from pymongo import MongoClient

def database():
    client = MongoClient('mongodb://localhost:27017/')
    return client['pharmacy_scraper']

    # client = MongoClient('mongodb+srv://username:password@scrap.czefu97.mongodb.net/development')
    # return client['development']