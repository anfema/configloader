from __future__ import annotations
from typing import Dict, Any, List, Optional
import os
import inspect

from yaml import load
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


class ConfigurationError(Exception):
    pass


def _merge(a: Any, b: Any) -> Any:
    """
    Merge two objects

    If ``a`` is a list:
        - If ``b`` is anything but a list ``b`` will be appended to that list
        - If ``b`` is a list too then ``b`` will extend ``a``
    
    If ``a`` is a dict, ``b`` must be a dict too and both dictionaries are recursively merged
    by calling the ``_merge()`` function again.

    If ``a`` is a primitive, the merge will return ``b``, so it can be used to override already
    set values while running the recursive merge.
    """
    key = None
    try:
        if a is None or isinstance(a, str) or isinstance(a, int) or isinstance(a, float) or isinstance(a, bool):
            # edge case for first run or if a is a primitive
            a = b
        elif isinstance(a, list):
            # lists can be only appended
            if isinstance(b, list):
                # merge lists
                a.extend(b)
            else:
                # append to list
                a.append(b)
        elif isinstance(a, dict):
            # dicts must be merged
            if isinstance(b, dict):
                for key in b:
                    if key in a:
                        a[key] = _merge(a[key], b[key])
                    else:
                        a[key] = b[key]
            else:
                raise ConfigurationError('Cannot merge non-dict "%s" into dict "%s"' % (b, a))
        else:
            raise ConfigurationError('NOT IMPLEMENTED "%s" into "%s"' % (b, a))
    except TypeError as e:
        raise ConfigurationError('TypeError "%s" in key "%s" when merging "%s" into "%s"' % (e, key, b, a))
    return a


def _delinearize(items: Dict[str, Any]) -> Dict[str, Any]:
    """
    Split items and build a tree if the keys are delimited with double underscores
    """
    result = {}
    for key, value in items.items():
        if not isinstance(value, list) and not isinstance(value, dict):
            path = key.split('__')
            last_item = result
            for item in path[:-1]:
                if item not in last_item:
                    last_item[item] = {}
                last_item = last_item[item]
            if value == 'null':
                last_item[path[-1]] = None
            else:
                last_item[path[-1]] = value
        else:
            result[key] = value
    return result


class Config(dict):
    def __init__(self, filename: Optional[str] = None):
        if filename is not None:
            with open(filename, 'r') as fp:
                self.merge(_delinearize(load(fp, Loader=Loader)))
    
    def merge(self, *items: Dict[str, Any]) -> Config:
        """
        Merge multiple configuration dicts into one

        :param items: list of items to merge
        :returns: a reference to self to be able to chain merges
        """
        for item in items:
            _merge(self, item)
        return self

    def add_file(self, filename: str) -> Config:
        """
        Add a file to the configuration

        This is primarily used by k8s when mounting a config map as a volume.
        The basename of the filename is delinearized and used as the key, the
        value is just the content of the file.
        """
        with open(filename, 'r') as fp:
            content = fp.read()
        item = {os.path.basename(filename): content}
        return self.merge(_delinearize(item))

    def merge_environment(self) -> Config:
        """
        Load values from environment variables that start with either
        ``CONFIG_` or with the ``environment_prefix`` that is configured before

        :returns: a reference to self to be able to chain merges
        """
        env = {}
        if 'environment_prefix' in self:
            prefix = self['environment_prefix']
        else:
            prefix = 'CONFIG_'
        items = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                path = key[len(prefix):].lower()
                items[path] = value
            # del os.environ[key] 
            #  I would like to do that, but it starves the worker processes from the
            #  needed secrets/overrides as the master process would unset the variable
            #  before starting the workers, which read the config from the environment
            #  again. As I have no means of detecting if we are in a worker or the
            #  master process we sadly have to let it stay in memory.
        env = _delinearize(items)
        return self.merge(env)


class Configuration:

    def __init__(self, base_name: str='backend'):
        self.config = Config()

        valid_paths = (
            os.path.expanduser('~/etc/'),
            os.path.dirname(os.path.dirname(os.path.abspath(inspect.stack()[1].filename ))),  # django project dir
            os.path.abspath('.')
        )
        valid_extensions = ('.yaml', '.yml')
        possible_locations = (
            (os.path.join(path, f'{base_name}{ext}'))
            for path in valid_paths
            for ext in valid_extensions
        )

        # Try to find a local config file
        for location in possible_locations:
            if os.path.isfile(location):
                config_file = location
                break
        else:
            config_file = None

        if config_file:
            self.config.merge(Config(config_file))
        else:
            # Try to fetch from yaml files, we're in a container, so we have k8s configmaps
            config_files = [os.path.join('/code/config', item) for item in sorted(os.listdir('/code/config'))]
            for config_file in config_files:
                if not os.path.isfile(config_file):
                    continue
                if os.path.splitext(config_file)[1] in valid_extensions:
                    self.config.merge(Config(config_file))
                else:
                    self.config.add_file(config_file)

            # Throw exception when no config was loaded
            if len(self.config.keys()) == 0:
                raise FileNotFoundError(f'/code/config/{base_name}.yaml')

            # This one may be missing if we're using env variables
            secret_files = [os.path.join('/code/secrets', item) for item in sorted(os.listdir('/code/secrets'))]
            for secret_file in secret_files:
                if not os.path.isfile(secret_file):
                    continue
                if os.path.splitext(secret_file)[1] in valid_extensions:
                    self.config.merge(Config(secret_file))
                else:
                    self.config.add_file(secret_file)

        self.config.merge_environment()

    def __getitem__(self, path: str):
        return self.get(path)

    def __contains__(self, path: str):
        try:
            self.get(path)
        except KeyError:
            return False
        return True

    def get(self, path: str) -> Any:
        """
        Return a configuration item by walking the ``.`` separated path and
        recursively fetching from the configuration tree.
        """
        items = path.split(".")
        base = self.config
        try:
            for item in items:
                base = base[item]
            return base
        except TypeError as e:
            raise ValueError('Can not fetch path {}, invalid type {}'.format(path, base.__class__.__name__))
