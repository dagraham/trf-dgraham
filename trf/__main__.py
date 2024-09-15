import sys

from .trf import main # This imports `main` from `trf/trf.py`

if __name__ == "__main__":
    print(f"calling trf.main() from __main__ with {sys.argv = }")
    main()
