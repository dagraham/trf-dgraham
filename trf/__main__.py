# trf/__main__.py
import sys
print(f"in __main__ with {sys.argv = }")
from . import db, connection, root, transaction
from .trf import main # This imports `main` from `trf/trf.py`
print("in __main__ after import main")
print(f"__main__ db: {db = }, {connection = }, {root = }, {transaction = }")
# tracker_manager = TrackerManager(db=db, connection=connection, root=root, transaction=transaction)
# print(f"tracker_manager: {tracker_manager.__dict__}")


if __name__ == "__main__":
    print(f"calling trf.main() from __main__ with {sys.argv = }")
    main()
# else:
#     print(f"not calling trf.main() with {sys.argv = }")
