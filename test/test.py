from configloader import Configuration
config = Configuration(base_name="test")

# Access keys with path-like strings like so:
print(config['toplevel.sublevel.xyz'])