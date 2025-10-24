from django.core.management.base import BaseCommand
import subprocess
import os
import sys

class Command(BaseCommand):
    help = 'Build Tailwind CSS for production'

    def handle(self, *args, **options):
        self.stdout.write('Building Tailwind CSS...')
        
        try:
            # Check if npm is available
            result = subprocess.run(['npm', '--version'], capture_output=True, text=True)
            if result.returncode != 0:
                self.stdout.write(self.style.WARNING('npm not found. Please install Node.js and npm.'))
                return
            
            # Build Tailwind CSS
            result = subprocess.run(['npm', 'run', 'build-css'], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS('Tailwind CSS built successfully!'))
            else:
                self.stdout.write(self.style.ERROR(f'Failed to build Tailwind CSS: {result.stderr}'))
                
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR('npm not found. Please install Node.js and npm.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error building Tailwind CSS: {str(e)}'))
