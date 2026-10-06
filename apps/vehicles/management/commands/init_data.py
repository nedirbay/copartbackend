from django.core.management.base import BaseCommand
from create_seed_data import create_seed

class Command(BaseCommand):
    help = "Populate initial seed data (dictionaries, admin, employees, sample vehicles)"

    def handle(self, *args, **options):
        self.stdout.write("Initializing initial system data...")
        create_seed()
        self.stdout.write(self.style.SUCCESS("Successfully populated initial data!"))
