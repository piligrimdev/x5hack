import os

from webx5.database.database import Database

db = Database(os.environ["DATABASE_URL"])
