import re
import sys
from briltxt_boru import bril2txt
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(bril2txt())
