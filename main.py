import calendar
import datetime
import multiprocessing
import sqlite3
import subprocess
import argparse
import time

from tqdm import tqdm

database_filename = "packages" + "_" + str(datetime.datetime.now()) + ".db"

parser = argparse.ArgumentParser()
# Set to True if you want to store the versions of installed packages in the database
parser.add_argument('-s', '--store_package_version', action='store_true', help='Store package version')
parser.add_argument('-d', '--database_name', default=database_filename, help='Name of the SQLite database')
args = parser.parse_args()

# Connection to SQLite database
with sqlite3.connect(args.database_name) as db_connection:
    cursor = db_connection.cursor()

    # Create packages table if not exists
    cursor.execute('''CREATE TABLE IF NOT EXISTS packages (name text, repository text, version text )''')

    # Command to execute
    command = "apt list --installed 2> /dev/null | cut -d/ -f1 | parallel -n200 apt-cache policy | rg '^(\S+)[\s\S]+?\* (?:\S+\s+){3}(\S+)' -Uor '$1 $2'"

    # Delete all records from the packages table
    cursor.execute('DELETE FROM packages;')
    db_connection.commit()
    package_names = []
    # Execute the command and iterate over the results
    try:
        output = subprocess.check_output(command, shell=True, text=True)
        total_lines = len(output.splitlines())
        print("Found " + str(total_lines) + " packages")

        # Insert data into the packages table
        for idx, line in enumerate(output.splitlines()):
            name, repository = line.split(' ')
            name = name[:-1].replace(':i386', '')
            package_names.append(name)
            version = None
            cursor.execute("INSERT INTO packages VALUES (?, ?, ?)", (name, repository, version))

            # Commit transaction every 1000 rows
            if idx % 1000 == 0:
                db_connection.commit()

        db_connection.commit()

        if args.store_package_version is True:
            print("Store version for " + str(total_lines) + " packages, please wait...")


            # Define update function
            def update_package(package_name):
                dpkg_output = subprocess.check_output(
                    'dpkg -l "{}" | grep "^ii" | awk \'{{print $3}}\''.format(package_name),
                    shell=True, text=True, stderr=subprocess.DEVNULL)
                package_version = dpkg_output.strip()
                if package_version:
                    cursor.execute('UPDATE packages SET version = ? WHERE name = ?', (package_version, package_name))
                    db_connection.commit()


            # Define parallel processing function
            def parallel_process(function, iterable, n_processes=multiprocessing.cpu_count()):
                with tqdm(total=len(iterable)) as pbar:
                    def update(*a):
                        pbar.update()

                    with multiprocessing.Pool(processes=n_processes) as pool:
                        for _ in pool.imap_unordered(function, iterable):
                            update()


            # Update packages
            parallel_process(update_package, package_names)

            # Save changes and close database connection
            db_connection.commit()

        # Execute query
        cursor = db_connection.cursor()
        query = 'SELECT repository, COUNT(*) FROM packages GROUP BY repository order by COUNT(*) DESC;'
        results = cursor.execute(query).fetchall()

        # Define separator
        separator = '{:<10} | {:<100}'.format('__________',
                                              '_______________________________________________________________________________________________________')

        # Print header
        print('{:>10} | {:<100}'.format('Count', 'Repository'))
        print(separator)

        # Print each row of results
        for row in results:
            count = row[1]
            repo = str(row[0])
            # Truncate repository name if it's longer than 100 characters
            if len(repo) > 100:
                repo = repo[:97] + "..."
            print('{:>10} | {:<100}'.format(count, repo))

        # Print footer
        print(separator)

        # db_connection.close()

    except subprocess.CalledProcessError as e:
        print("Error during command execution: ", e)
