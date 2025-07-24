Jobsite Address Geocoder (Real Google Maps Version)

This script automates the process of:
1.	Loading a cleaned and sorted jobsite list from an Excel file
2.	Parsing the full address column into structured components (Street, City, State, ZIP)
3.	Geocoding each address using the Google Maps API
4.	Saving the final result to a CSV file for further use or visualization (e.g., Google My Maps)
________________________________________
Folder Structure

your_project_folder/
├── jobsite_sort_geocode.py       ← The script
├── Sorted_Jobsite_List.xlsx      ← Input Excel file with Name + Address columns
├── Geocoded_Jobsites.csv         ← Output file with real coordinates
├── README.md                     ← This file
________________________________________
Requirements

•	Python 3.8+
•	Install dependencies:
 	pip install pandas openpyxl requests
•	A Google Cloud account with the Geocoding API enabled
________________________________________
How to Use

1. Prepare your input Excel file
Your Excel file must contain at least the following columns:
•	Name – the jobsite name
•	Address – full address in format:
123 Main St, Atlanta, GA 30301
2. Insert your API Key
In the script file jobsite_sort_geocode.py, replace the placeholder:
GOOGLE_API_KEY = "your_api_key_here"
With your actual Google Maps API key.
3. Run the script
Use your terminal, command prompt, or VSCode:
python jobsite_sort_geocode.py
4. Output
The script will generate:
•	A CSV file named Geocoded_Jobsites.csv
•	It contains:
o	Name
o	Address
o	Street, City, State, ZIP (parsed from address)
o	Latitude, Longitude (real coordinates)
________________________________________
Getting Your Google Maps API Key

1.	Go to https://console.cloud.google.com/
2.	Create a project (or use an existing one)
3.	Go to APIs & Services > Library and enable:
o	Geocoding API
4.	Go to APIs & Services > Credentials
5.	Click Create Credentials > API Key
6.	Copy and paste the key into your script
________________________________________
Example Use Cases

•	Visualizing jobsite groups on a map
•	Planning driving routes by location
•	Organizing jobs by geographic proximity
________________________________________
Troubleshooting

Issue	Solution
FileNotFoundError	Make sure the Excel file is in the same directory and the name matches exactly
ModuleNotFoundError	Run pip install pandas openpyxl requests
NaN Latitude/Longitude	Happens if Google Maps can’t find the address — check formatting
REQUEST_DENIED	Ensure billing is enabled and key is authorized for Geocoding API
________________________________________
Optional: Create a .bat File (Windows)

To run the script with a double-click:
1.	Open Notepad and paste:
@echo off
python "C:\Path\To\jobsite_sort_geocode.py"
pause
2.	Save as: run_geocoder.bat
3.	Double-click to run
________________________________________
