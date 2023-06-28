import json
from getpass import getpass

import _activate_django  # pyright: ignore[reportUnusedImport] # pylint: disable=W0611
from common.constants import BASE_DIR
from common.credential_mangement import Credentials
from json_file import JSONFile


def main() -> None:
    password = getpass("Credentials password")
    credentials = Credentials.load_credentials(password)

    JSONFile(BASE_DIR / "secret_management" / "credentials.json").write(json.dumps(credentials))


if __name__ == "__main__":
    main()
