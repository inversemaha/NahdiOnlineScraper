# Product Description Updater – How to Run

## Command Line Usage
To update all product descriptions in your database, run this command in your terminal:

```bash
python product_description_service.py
```

This will start the updater, which fetches and saves product descriptions for all products that need them.

## What Happens When You Run It
- The script prints which product URL is being requested and whether the update was successful.
- Updates are processed in batches for efficiency.
- At the end, you'll see a summary of the update process.

## Requirements
- Python 3.10+
- MongoDB running and accessible
- ChromeDriver installed and available in your PATH
- All dependencies from `requirements.txt` installed

## Troubleshooting
- If you see errors about ChromeDriver, make sure it matches your Chrome version and is installed correctly.
- For database connection issues, check your MongoDB configuration in `database.py`.

---
For API usage or integration, see the API documentation or contact your technical team.
