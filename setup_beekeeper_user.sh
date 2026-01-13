#!/bin/bash
# Report script to create a user for Beekeeper Studio

echo "--------------------------------------------------------"
echo "Setting up 'beekeeper' user for Database Access..."
echo "--------------------------------------------------------"

# Run SQL commands as root via sudo
sudo mysql -u root -e "CREATE USER IF NOT EXISTS 'beekeeper'@'%' IDENTIFIED BY 'beekeeper123';"
sudo mysql -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'beekeeper'@'%' WITH GRANT OPTION;"
sudo mysql -u root -e "FLUSH PRIVILEGES;"

echo "--------------------------------------------------------"
echo "Success! A new database user has been created."
echo ""
echo "Please use these credentials in Beekeeper Studio:"
echo "Connection Type: MySQL"
echo "Host:            localhost"
echo "User:            beekeeper"
echo "Password:        beekeeper123"
echo "Default Database: missing_persons_db"
echo "--------------------------------------------------------"
