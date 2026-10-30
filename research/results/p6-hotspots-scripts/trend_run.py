import sys
import importlib
run = importlib.import_module("rangtoy." + sys.argv[1]).run
run(sys.argv[2], sys.argv[3])
