# TODO: Eventually allow configuration through the web interface
from getpass import getpass
import _activate_django  # pyright: ignore[reportUnusedImport] # pylint: disable=W0611

from common.scrapers import Scraper

from common.credential_mangement import Credentials


def main() -> None:
    password = getpass("Credentials password")

    # If the credential file doesn't exist create it
    if not Credentials.CREDENTIALS_FILE.exists():
        Credentials.dump_credentials({}, password)

    # Load credentials
    credentials = Credentials.load_credentials(password)

    # Display a list of scrapers
    for i, credential_keys in enumerate(Scraper.credential_keys()):
        print(f"{i}. {credential_keys[0]}")

    scraper_index = int(input("Choose scraper number to configure"))

    # It's easier to work with the tuple when all values are expanded out into variables
    scraper_tuple = Scraper.credential_keys()[scraper_index]
    scraper_name = scraper_tuple[0]
    scraper_keys = scraper_tuple[1]
    for key in scraper_keys:
        # Create key for scraper if needed
        if scraper_name not in credentials:
            credentials[scraper_name] = {}

        credentials[scraper_name][key] = getpass(f"{scraper_name}: {key}:")

    Credentials.dump_credentials(credentials, password)


if __name__ == "__main__":
    main()
