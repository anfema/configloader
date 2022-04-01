# Configuration loader

## Installation

add via pip:

```
pip install https://github.com/anfema/configloader/releases/1.0/download/configloader-1.0.0-py3-none-any.whl
```

## Usage

### Python

```python
from configloader import Configuration
config = Configuration(base_name="backend")

# Access keys with path-like strings like so:

xyz = config['toplevel.sublevel.xyz']
```

### Config files

YAML config files are searched in this order:

- `$HOME/etc/backend.yaml`
- `$HOME/etc/backend.yml`
- `./backend.yaml`
- `./backend.yml`

if you initialized with another `base_name`, replace `backend` with that.

YAML config file example:

```yaml
toplevel:
  sublevel:
    xyz: "bla"
```

### Overriding configuration

To override configuration from config files you can set environment variables.
By default we search for env variables beginning with `CONFIG_`, you can override
this prefix by setting `environment_prefix` in a YAML config that is loaded before
overrides are processed.

All env variables are stripped of their prefix and then lowercased and _delinearized_
(see below).

Example override:

```bash
export CONFIG_TOPLEVEL__SUBLEVEL__XYZ="bla"
```

### Alternative config file formats

If none of the default config files can be found we try to load alternatives
from alternative locations (mostly to be able to use K8S configmaps mouted as volumes):

- We check if we can find any files in `/code/config`
   - If we find `yml` or `yaml` files those are loaded like normal YAML files
   - If we find files without an extension we load the content with the name of the
     file as a key.
- The same happens for `/code/secrets`
- All keys found this way are _delinearized_ (see below)

Example YAML:

```yaml
toplevel__sublevel__xyz: "bla"
```

Example bare config file:

```
$ ls /code/config
toplevel__sublevel__xyz

$ cat /code/config/toplevel__sublevel__xyz
bla
```

### Delinearization

If the keys contain double underscores we split them up into key-paths like
the django ORM would do: `subkey__key` will be split into `subkey` with a
member `key`.

Setting values to `null` will result in `None` at the python side.

