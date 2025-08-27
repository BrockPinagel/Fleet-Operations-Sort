# Fleet Operations Jobsite Clustering

This project provides a Python program for clustering job sites geographically, assigning them into groups with constraints, and exporting the results for further use in spreadsheets or Google Earth Pro.

## Overview

The script reads jobsite data from an Excel file, geocodes the addresses using the Google Maps API, and then clusters the jobs into groups using the KMeans algorithm. Groups are capped at 16 jobs each. Groups are also renumbered based on their proximity to a central shop address, so Group 0 is the closest, Group 1 is the next closest, and so on.

The script provides an interactive interface that allows the user to select the number of groups (K) to generate. After running once, it will continue to prompt the user to run again with a different number of groups until the user cancels.

## Features

- Reads jobs from an Excel file (`Jobsite_List.xlsx`) with columns for Name, Address, and optional Latitude/Longitude.
- Geocodes addresses using the Google Maps API. Results are cached locally in `geocode_cache.csv` to avoid redundant API calls.
- Clusters jobs geographically using KMeans. The number of clusters (K) is chosen by the user via a simple entry dialog box.
- Enforces a hard cap of 16 jobs per group by reassigning jobs as needed to the nearest group with capacity.
- Renumbers groups by proximity to the shop address, ensuring group order matches physical closeness to the depot.
- Outputs four files:
  - `Jobs_Inner.csv`: jobs in the closest half of the groups
  - `Jobs_Outer.csv`: jobs in the furthest half of the groups
  - `Grouped_Geocoded_Jobsites.csv`: all jobs with their group assignment
  - `Grouped_Jobs.kml`: KML file with one folder per group, usable in Google Earth Pro

## Requirements

- Python 3.11 or later
- The following Python packages (see requirements.txt):
  - pandas
  - numpy
  - scikit-learn
  - scipy
  - requests
  - openpyxl
  - xlrd
  - python-dotenv

Install them with:

```
pip install -r requirements.txt
```

## Setup

1. Place your input Excel file (`Jobsite_List.xlsx`) in the working directory. It must contain at least a Name column and an Address column. Latitude and Longitude columns are optional; if absent, they will be filled via geocoding.
2. Place the script (`JobsiteSortV3.py` or `jobsite_sort_geo_cap16_ui.py`) in the same directory.
3. Create a `.env` file or set environment variables with your Google Maps API key:

```
GOOGLE_API_KEY=your_api_key_here
```

4. Optionally override other variables in `.env` or environment:
   - `SHOP_ADDRESS` (default: 414 Hadley street holly michigan 48442)
   - `MAX_PER_GROUP` (default: 16)

## Running

You can run the program by double-clicking the batch file `run_jobsites_ui.bat` or from the command line:

```
python jobsite_sort_geo_cap16_ui.py
```

When run without arguments, the script will open a dialog to ask for the number of groups (K). After each run, it will ask if you would like to choose a different number. This repeats until you cancel.

To run once with a fixed K:

```
python jobsite_sort_geo_cap16_ui.py --k 38
```

## Outputs

- `Jobs_Inner.csv`: jobs belonging to the closest half of the groups
- `Jobs_Outer.csv`: jobs belonging to the furthest half of the groups
- `Grouped_Geocoded_Jobsites.csv`: master file with all jobs and their group assignments
- `Grouped_Jobs.kml`: Google Earth Pro KML with groups organized into folders

## Troubleshooting

### Missing Python packages

If you see errors like `ModuleNotFoundError: No module named 'pandas'` or `No module named 'requests'`, install dependencies with:

```
pip install -r requirements.txt
```

### Missing openpyxl

If you see `ImportError: Missing optional dependency 'openpyxl'`, install it with:

```
pip install openpyxl
```

### Google Maps API errors

- Make sure you have a valid Google Maps Geocoding API key.
- Ensure that your billing is enabled in the Google Cloud Console.
- Watch for daily quota limits. Caching in `geocode_cache.csv` will help minimize repeated calls.

### No jobs with coordinates

If you see `No jobs with coordinates; skipping.`, check that your input Excel file has a valid Address column and that the API key is set correctly.

### CSV vs KML in Google Earth Pro

If you import the CSV files into Google Earth Pro, all jobs will appear flat with no folder grouping. Use the KML file instead. It creates a folder per group, which you can toggle on and off.

## License

This project is provided as-is for demonstration purposes. Adapt and extend as needed for production use.
