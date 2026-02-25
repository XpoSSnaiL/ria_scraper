import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def create_db_dump():
    print("Starting database dump...")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_name = os.getenv("DB_NAME")

    # Create folder if it doesn't exist
    os.makedirs("dumps", exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_path = f"dumps/dump_{date_str}.sql"

    os.environ["PGPASSWORD"] = db_password
    command = f"pg_dump -h {db_host} -U {db_user} -d {db_name} -F c -f {file_path}"

    result = os.system(command)

    if result == 0:
        print(f"Dump successful: {file_path}")
    else:
        print("Error during database dump!")