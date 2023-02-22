import sqlite3
import subprocess
from multiprocessing import Pool
import multiprocessing

# Set to True if you want to store the versions of installed packages in the database
store_package_version = False

# Connection to SQLite database
with sqlite3.connect('packages.db') as db_connection:
    cursor = db_connection.cursor()

    # Create packages table if not exists
    cursor.execute('''CREATE TABLE IF NOT EXISTS packages (name text, repository text, version text )''')

    # Command to execute
    command = "apt list --installed 2> /dev/null | cut -d/ -f1 | parallel -n200 apt-cache policy | rg '^(\S+)[\s\S]+?\* (?:\S+\s+){3}(\S+)' -Uor '$1 $2'"

    # Delete all records from the packages table
    cursor.execute('DELETE FROM packages;')
    db_connection.commit()
    # Execute the command and iterate over the results
    try:
        output = subprocess.check_output(command, shell=True, text=True)
        for line in output.splitlines():
            name, repository = line.split(' ')
            name = name[:-1].replace(':i386', '')
            version = None
            # Insert data into the packages table
            cursor.execute("INSERT INTO packages VALUES (?, ?, ?)", (name, repository, version))

        db_connection.commit()

        if store_package_version is True:
            # Execute query
            query = 'SELECT name FROM packages;'
            results = cursor.execute(query).fetchall()

            # Split the package names into chunks of size 100
            chunks = [results[i:i + 100] for i in range(0, len(results), 100)]


            def update_packages(package_chunk):
                for my_package in package_chunk:
                    package_name = my_package[0]
                    apt_output = subprocess.check_output("apt list --installed | grep " + package_name, shell=True,
                                                         text=True,
                                                         stderr=subprocess.DEVNULL)
                    package_version = apt_output.split()[1]
                    cursor.execute("UPDATE packages SET version = ? where name = ?", (package_version, package_name))
                    db_connection.commit()


            # Use multiprocessing to update packages in parallel
            with Pool(processes=multiprocessing.cpu_count()) as pool:
                pool.map(update_packages, chunks)

            # Save changes
            db_connection.commit()

        # Execute query
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

    except subprocess.CalledProcessError as e:
        print("Error during command execution: ", e)
