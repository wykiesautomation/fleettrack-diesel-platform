"""List local COM/serial ports without opening or changing them."""
import json
from .runtime import available_ports
if __name__=='__main__':print(json.dumps(available_ports(),indent=2))
