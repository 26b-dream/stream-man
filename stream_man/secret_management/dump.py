import json
from getpass import getpass

import _activate_django  # pyright: ignore[reportUnusedImport] # pylint: disable=W0611
from common.constants import BASE_DIR
from common.credential_mangement import Credentials
from json_file import JSONFile


def main() -> None:
    Credentials.login()
    credentials = Credentials.load_credentials()

    JSONFile(BASE_DIR / "secret_management" / "credentials.json").write(json.dumps(credentials))


if __name__ == "__main__":
    main()
