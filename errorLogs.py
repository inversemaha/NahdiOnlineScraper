import sys
from datetime import datetime
from pymongo import MongoClient
from database import database
import utils as u

url='url'
exceptionType='exceptionType'
exceptionObject='exceptionObject'
lineNumber='lineNumber'
pharmacy='pharmacy'
insertedAt='insertedAt'
name='name'
startedAt='startedAt'
pageLength='pageLength'
endAt='endAt'
countries = "countries"
errorAt = "errorAt"
completedAt = "completedAt"

def time():
    now = datetime.now()
    return now

db = database()

def errorInsert(context, exception_type, exception_object, line_number, source=""):
    try:
        collection = db['pharmacystores']
        error_doc = {
            "context": context,
            "exception_type": str(exception_type),
            "exception_object": str(exception_object),
            "line_number": line_number,
            "source": source,
            "timestamp": datetime.utcnow()
        }
        collection.insert_one(error_doc)
        print(f"[Error Logged] {source} - {exception_type} at line {line_number}")
    except Exception as e:
        print(f"Failed to log error: {e}")
def logsInsert(_name, _pageLength=None):
    try:
        collection = db['pharmacystores']
        collection.update_one({name: _name,}, {"$set": {startedAt: datetime.now()}})

        collection = db['logs']
        d1 = {
            name: _name,
            startedAt: time(),
        }
        if _pageLength is not None:
            d1[pageLength] = _pageLength
        return collection.insert_one(d1)
    except:
        pass

def logUpdate(_logId, _pageLength=None):
    try:
        d1={
            endAt:time()
        }
        if _pageLength is not None:
            d1[pageLength] = _pageLength
        collection = db['logs']
        collection.update_one({'_id':_logId.inserted_id},{ "$set": d1})

        #update counted pharmacy in pharmacystores collection
        data = collection.find_one({'_id':_logId.inserted_id})

        collectedPharmacy = next((pharmacy for pharmacy in u.countList if pharmacy[u.pharmacyName] == data['name']), None)
        if collectedPharmacy:
            collection = db['pharmacystores']
            myquery = {u.name:data['name']}
            newvalues = { "$set": collectedPharmacy}
            collection.update_one(myquery, newvalues)
            u.removePharmacy(data['name'])
    except:
        pass

#for pharmacies
def LastScrapperTimeUpdate(pharmacyStoreId, collection, _countries):
    try:
        collection = db['pharmacystores']
        # collection.update_one({"_id": pharmacyStoreId}, {"$set": {startedAt: datetime.now(), countries:_countries}})

        collection.update_one({"_id": pharmacyStoreId},{"$set":{completedAt : datetime.now(), countries:_countries},"$unset": {exceptionType: "", exceptionObject: "", lineNumber: "", errorAt: ""}})

    except Exception as e:
        print("Error:", e)
