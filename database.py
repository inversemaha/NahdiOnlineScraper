from pymongo import MongoClient

def database():
    client = MongoClient('mongodb://localhost:27017/')
    return client['pharmacy_scraper']
