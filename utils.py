from datetime import datetime
import os.path
import sys
sys.path.append(os.path.dirname(os.path.abspath("__file__")))
from database import database
import re
import requests
import pandas as pd
import random
from errorLogs import errorInsert
#from services.vooyfarma.service import notifyPriceChangeRequest
import unidecode
from pymongo import UpdateOne
from concurrent.futures import ThreadPoolExecutor
import threading

insert_lock = threading.Lock()

db = database()
collection = db['pharmacies']

df=pd.read_csv('proxies.csv')

df=df['proxy'].to_list()
allProxy= []
def webshare_proxy_list():
    if not allProxy:
        response = requests.get(
        "https://proxy.webshare.io/api/proxy/list/?page_size=1000",
        headers={"Authorization": ""}
        )
        for proxy in response.json()['results']:
            allProxy.append(proxy['proxy_address']+":"+str(proxy['port']))

    return allProxy.pop(0)
def random_proxy():
    pr=random.choice(df)
    return ''+pr
def get_proxy():
    prox= random_proxy()
    proxy={'http':prox,
       'https':prox}
    return proxy

def to_camel_case(text):
    text = unidecode.unidecode(text)
    words = text.split()
    camel_case_text = words[0].lower() + ''.join(word.capitalize() for word in words[1:])
    return camel_case_text

#add in each pharmacy
def web_share_proxy():
    return {'http':webshareProxy,
       'https':webshareProxy}

def dataImpulseProxy(countryCode = None):
    if countryCode:
       proxies = {
            'http': f'http://username:password@gw.dataimpulse.com:823',
            'https': f'http://username:password@gw.dataimpulse.com:823',
        }
    else:
            proxies = {
            'http': 'http://username:password@gw.dataimpulse.com:823',
            'https': 'http://username:password@gw.dataimpulse.com:823',
        }
        
    return proxies

pharmacyName='Pharmacyname'
url='URL'
category='Category'
product='Product'
price='Price'
cutPrice='CutPrice'
image='Image'
startedAt='startedAt'
endAt='endAt'
createdAt='createdAt'
updatedAt='updatedAt'
amount='amount'
tPrice='price'
extraInfo='ExtraInfo'
ingredientes='Ingredientes'
pharmacyStoreId='pharmacyStoreId'
pageLength='pagelength'
features='features'
description='description'
name='name'
presentation='presentation'
categorySlug='categorySlug'
medicineSlug='medicineSlug'
outOfStock='outOfStock'
isActive='isActive'
scrapperUrl="scrapperUrl"
priceChange='priceChange'
country='country'
date='date'
marca='Marca'
originalPrice='originalPrice'
originalPriceCurrency='originalPriceCurrency'
lastScrappedTime = "lastScrappedTime"
isDeleted = "isDeleted"
normalizedName = "normalizedName"
managerPublicName = "managerPublicName"
speciality ="speciality"
pharmacyNameSlug ="pharmacyNameSlug"
provider = "provider"
title = "title"
questionAnswers = "questionAnswers"
rating = "rating"
reviews = "reviews"
accordions = "accordions"
subtitle = "subtitle"
countryOrigin = "countryOrigin"
originCountry = "originCountry"
scrapped = "scrapped"
conversionRate = "conversionRate"


insertLimit = 100

proxy=get_proxy()
webshareProxy='http://username:password@p.webshare.io:80/'

def get_cleaned_cat(text, key):
    if not text:
        return ""

    split_text = text.strip().lower()

    # Replace spaces and slashes with dashes
    split_text = re.sub(r"[\s/]", "-", split_text)

    # Remove brackets and other special characters, keeping only alphanumeric characters and dashes
    split_text = re.sub(r"[^\w-]", "", split_text)

    # Replace multiple consecutive dashes with a single dash
    split_text = re.sub(r"-+", "-", split_text)
    if key == medicineSlug:
        if collection.count_documents({medicineSlug:split_text}) > 1:
            if not split_text.split('-')[-1].isdigit():
                split_text = split_text + "-1"
            else:
                split_text = "-".join(split_text.split('-')[:-2]) + "-"+str(int(split_text.split('-')[-1])+1)

    return unidecode.unidecode(split_text)

#count the insert and update in separate pharmacy
countList = []

def itemCount(_pharmacyname, _country, action):
    pharmacy = next((item for item in countList if item[pharmacyName] == _pharmacyname), None)
    if pharmacy is None:
        pharmacy = {pharmacyName: _pharmacyname, "countries": [], "summary": []}
        countList.append(pharmacy)
    
    if _country not in pharmacy["countries"]:
        pharmacy["countries"].append(_country)
    
    country_data = next((item for item in pharmacy["summary"] if item["country"] == _country), None)
    if country_data is None:
        country_data = {"country": _country, "insert": 0, "update": 0}
        pharmacy["summary"].append(country_data)
    
    country_data[action] += 1

#remove the counted pharmacy
def removePharmacy(_pharmacyname):
    global countList
    countList = [pharmacy for pharmacy in countList if pharmacy[pharmacyName] != _pharmacyname]

def handle_split(text):
    if not text:
        return ""

    split_text = text.strip().lower()

    # Replace spaces and slashes with dashes
    split_text = re.sub(r"[\s/]", "-", split_text)

    # Remove brackets and other special characters, keeping only alphanumeric characters and dashes
    split_text = re.sub(r"[^\w-]", "", split_text)

    # Replace multiple consecutive dashes with a single dash
    split_text = re.sub(r"-+", "-", split_text)

    return split_text

def time():
    now = datetime.now()
    return now

def insert(_pharmacyname,_url,_pharmacyStoreId,_category,_product,_price,_cutPrice,_img,_ingrads,_description,_presentation, _country=None, _marca=None, _originalPrice=None, _originalPriceCurrency=None, _managerPublicName=None, _speciality = None, _extraInfo = None, _provider = None, _extra = None, _title = None, _questionAnswers = None, _rating = None, _reviews = None, _accordions = None, _subtitle = None, _especialidad = None, _countryOrigin = None):
    try:
        if _country==None:
            _country="Mexico"
        if _marca==None:
            _marca=''
        if _price==None or _price=='' or _price==0 or _price == outOfStock:
            _price='0'
            _amount=0
            _outOfStock=True 
        else:
            _amount=float(_price.replace(",",'').replace('$','').replace('Q',''))
            _outOfStock=False
        
        d1={
            pharmacyName:_pharmacyname, #string
            url:_url, #string
            pharmacyStoreId:_pharmacyStoreId, #string
            category:_category, #string
            product:_product, #string
            normalizedName : unidecode.unidecode(_product),
            price:_price, #string
            outOfStock:_outOfStock,
            cutPrice:_cutPrice, #string
            image:_img, #list
            amount: _amount, #int
            createdAt:time(),
            updatedAt:time(),
            country:_country, #string
            marca:_marca, #string
            speciality : _speciality, #list
            extraInfo:{ 
            ingredientes:_ingrads, #list
            description:_description, #string
            presentation:_presentation, #string
            originalPriceCurrency:_originalPriceCurrency, #string
            originalPrice:_originalPrice #string
                    },
            categorySlug:get_cleaned_cat(_category, categorySlug),
            medicineSlug:get_cleaned_cat(_product, medicineSlug),
            pharmacyNameSlug:get_cleaned_cat(_pharmacyname, pharmacyNameSlug),
            priceChange:[{tPrice:_amount,date:time()}],
            isDeleted : False,
            managerPublicName : _managerPublicName,
            provider : _provider, 
            title :_title,
            questionAnswers : _questionAnswers,
            rating : _rating,
            reviews : _reviews,
            accordions : _accordions,
            subtitle : _subtitle,
            countryOrigin :_countryOrigin,
            scrapped: True
        }
        if _extraInfo:
            d1.update(_extraInfo)
        if _extra:
            d1.update(_extra)
        collection.insert_one(d1)
        itemCount(_pharmacyname, _country, "insert")
        print("insert", _url)
    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print('Utills error')
        print(_url)
        print("Exception type: ", exception_type)
        print("exception_object: ", exception_object)
        print("Line number: ", line_number)
        errorInsert(_url,exception_type,exception_object,line_number,"Utills Error")

def update(_pharmacyname,_url,_pharmacyStoreId,_category,_product,_price,_cutPrice,_img,_ingrads,_description,_presentation, _country=None, _marca=None, _originalPrice=None, _originalPriceCurrency=None, _managerPublicName=None, _speciality=None, _extraInfo = None, _provider = None, _extra = None, _title = None, _questionAnswers = None, _rating = None, _reviews = None, _accordions = None, _subtitle = None, _especialidad = None, _countryOrigin = None):
    try:
        if _country==None:
            _country="Mexico"
        if _marca==None:
            _marca=''
        if _price==None or _price=='' or _price==0 or _price == outOfStock:
            _price='0'
            _amount=0
            _outOfStock=True 
        else:
            _amount=float(_price.replace(",",'').replace('$','').replace('Q',''))
            _outOfStock=False
        
        data=collection.find_one({url:_url})

        if data["amount"] < _amount: 
            notifyPriceChangeRequest(str(data["_id"]))

        _priceChange=data[priceChange]
        _priceChange.append({tPrice:_amount,date:time()})
        d1={
            pharmacyName:_pharmacyname,
            pharmacyStoreId:_pharmacyStoreId,
            category:_category,
            product:_product,
            normalizedName : unidecode.unidecode(_product),
            price:_price,
            outOfStock:_outOfStock,
            cutPrice:_cutPrice,
            image:_img,
            amount:_amount,
            updatedAt:time(),
            country:_country,
            marca:_marca,
            speciality : _speciality,
            extraInfo:{ 
            ingredientes:_ingrads,
            description:_description,
            presentation:_presentation,
            originalPriceCurrency:_originalPriceCurrency,
            originalPrice:_originalPrice
                },
            categorySlug:get_cleaned_cat(_category, categorySlug),
            medicineSlug:get_cleaned_cat(_product, medicineSlug),
            pharmacyNameSlug:get_cleaned_cat(_pharmacyname, pharmacyNameSlug),
            priceChange:_priceChange,
            isDeleted : False,
            managerPublicName :_managerPublicName,
            provider : _provider,
            title :_title,
            questionAnswers : _questionAnswers,
            rating : _rating,
            reviews : _reviews,
            accordions : _accordions,
            subtitle : _subtitle,
            countryOrigin :_countryOrigin,
            scrapped: True
            }
        if _pharmacyname == "DrugsCom":
            myquery = { url: _url, product:_product} 
        else:   
            myquery = { url: _url}
        if createdAt not in data:
            d1.update({createdAt:time()})
        if _extraInfo:
            d1.update(_extraInfo)
        if _extra:
            d1.update(_extra)
        newvalues = { "$set": d1}
        collection.update_one(myquery, newvalues)
        itemCount(_pharmacyname, _country, "update")
        print("update", _url)
    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print('Utills error')
        print(_url)
        print("Exception type: ", exception_type)
        print("exception_object: ", exception_object)
        print("Line number: ", line_number)
        errorInsert(_url,exception_type,exception_object,line_number,"Utills Error")

#Extrainformation
def insert_extra(_pharmacyname,_url,_pharmacyStoreId,_category,_product,_price,_cutPrice,_img,_ingrads,_description,_presentation,_extra, _country=None, _marca=None, _countryOrigin = None):
    try:
        if _country==None:
            _country="Mexico"
        if _marca==None:
            _marca=''
        if _price==None or _price=='' or _price==0 or _price == outOfStock:
            _price='0'
            _amount=0
            _outOfStock=True 
        else:
            _amount=float(_price.replace(",",'').replace('$',''))
            _outOfStock=False
        
        d1={
            pharmacyName:_pharmacyname,
            url:_url,
            pharmacyStoreId:_pharmacyStoreId,
            category:_category,
            product:_product,
            normalizedName : unidecode.unidecode(_product),
            price:_price,
            outOfStock:_outOfStock,
            cutPrice:_cutPrice,
            image:_img,
            amount: _amount,
            createdAt:time(),
            updatedAt:time(),
            country:_country,
            marca:_marca,
            extraInfo:{ 
            ingredientes:_ingrads,
            description:_description,
            presentation:_presentation
                    },
            categorySlug:get_cleaned_cat(_category, categorySlug),
            medicineSlug:get_cleaned_cat(_product, medicineSlug),
            pharmacyNameSlug:get_cleaned_cat(_pharmacyname, pharmacyNameSlug),
            priceChange:[{tPrice:_amount,date:time()}],
            isDeleted : False,
            countryOrigin :_countryOrigin,
            scrapped: True
        }
        if _extra:
            d1.update(_extra)
        collection.insert_one(d1)
        itemCount(_pharmacyname, _country, "insert")
        print("insert", _url)
    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print('Utills error')
        print(_url)
        print("Exception type: ", exception_type)
        print("exception_object: ", exception_object)
        print("Line number: ", line_number)
        errorInsert(_url,exception_type,exception_object,line_number,"Utills Error")

def update_extra(_pharmacyname,_url,_pharmacyStoreId,_category,_product,_price,_cutPrice,_img,_ingrads,_description,_presentation,_extra, _country=None, _marca=None, _countryOrigin = None):
    try:
        if _country==None:
            _country="Mexico"
        if _marca==None:
            _marca=''
        if _price==None or _price=='' or _price==0 or _price == outOfStock:
            _price='0'
            _amount=0
            _outOfStock=True 
        else:
            _amount=float(_price.replace(",",'').replace('$',''))
            _outOfStock=False
        data=collection.find_one({url:_url})
        _priceChange=data[priceChange]
        _priceChange.append({tPrice:_amount,date:time()})

        d1={
            pharmacyName:_pharmacyname,
            pharmacyStoreId:_pharmacyStoreId,
            category:_category,
            product:_product,
            normalizedName : unidecode.unidecode(_product),
            price:_price,
            outOfStock:_outOfStock,
            cutPrice:_cutPrice,
            image:_img,
            amount:_amount,
            updatedAt:time(),
            country:_country,
            marca:_marca,
            extraInfo:{ 
            ingredientes:_ingrads,
            description:_description,
            presentation:_presentation
                },
            categorySlug:get_cleaned_cat(_category, categorySlug),
            medicineSlug:get_cleaned_cat(_product, medicineSlug),
            pharmacyNameSlug:get_cleaned_cat(_pharmacyname, pharmacyNameSlug),
            priceChange:_priceChange,
            isDeleted : False,
            countryOrigin :_countryOrigin,
            scrapped: True
            }
        myquery = { url: _url}
        if _extra:
            d1.update(_extra)
        if createdAt not in data:
            d1.update({createdAt:time()})
        newvalues = { "$set": d1}
        
        collection.update_one(myquery, newvalues)
        itemCount(_pharmacyname, _country, "update")
        print("Update ", _url)
    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print('Utills error')
        print(_url)
        print(_extra)
        print("Exception type: ", exception_type)
        print("exception_object: ", exception_object)
        print("Line number: ", line_number)
        errorInsert(_url,exception_type,exception_object,line_number,"Utills Error")

def bulkInsert(bulk_operations, _pharmacyname,_url,_pharmacyStoreId,_category,_product,_price,_cutPrice,_img,_ingrads,_description,_presentation, _country=None, _marca=None, _originalPrice=0, _originalPriceCurrency=None, _managerPublicName=None, _speciality = None, _extraInfo = None, _provider = None, _extra = None, _title = None, _questionAnswers = None, _rating = None, _reviews = None, _accordions = None, _subtitle = None, _especialidad = None,_query = None, _countryOrigin = None, _conversionRate=None):
    try:
        if _country==None:
            _country="Mexico"
        if _marca==None:
            _marca=''
        if _price==None or _price=='' or _price==0 or _price == outOfStock:
            _price='0'
            _amount=0
            _outOfStock=True 
        else:
            _amount=float(_price.replace(",",'').replace('$','').replace('Q',''))
            _outOfStock=False
        
        d1={
            pharmacyName:_pharmacyname, #string
            url:_url, #string
            pharmacyStoreId:_pharmacyStoreId, #string
            category:_category, #string
            product:_product, #string
            normalizedName : unidecode.unidecode(_product),
            price:_price, #string
            outOfStock:_outOfStock,
            cutPrice:_cutPrice, #string
            image:_img, #list
            amount: _amount, #int
            # createdAt:time(),
            updatedAt:time(),
            country:_country, #string
            marca:_marca, #string
            speciality : _speciality, #list
            extraInfo:{ 
            ingredientes:_ingrads, #list
            description:_description, #string
            presentation:_presentation, #string
            originalPriceCurrency:_originalPriceCurrency, #string
            originalPrice:_originalPrice #string
                    },
            categorySlug:get_cleaned_cat(_category, categorySlug),
            medicineSlug:get_cleaned_cat(_product, medicineSlug),
            pharmacyNameSlug:get_cleaned_cat(_pharmacyname, pharmacyNameSlug),
            # priceChange:[{tPrice:_amount,date:time()}],
            isDeleted : False,
            managerPublicName : _managerPublicName,
            provider : _provider, 
            title :_title,
            questionAnswers : _questionAnswers,
            rating : _rating,
            reviews : _reviews,
            accordions : _accordions,
            subtitle : _subtitle,
            countryOrigin :_countryOrigin,
            originCountry : _countryOrigin,
            scrapped: True
        }
        if _extraInfo:
            d1.update(_extraInfo)
        if _extra:
            d1.update(_extra)
        
        if not _query:
            _query = {url:_url}

        _priceChange = {price: _amount, date: time(), originalPrice:float(_originalPrice), conversionRate:_conversionRate, originalPriceCurrency:_originalPriceCurrency}
        bulk_operations.append( UpdateOne(
            _query,
            {
                "$set": d1,
                "$push": {
                    priceChange: _priceChange
                }
            }
                )
            )
            # Operation for inserting a new document if no match is found
        bulk_operations.append(UpdateOne(
            _query,
            {
                "$setOnInsert": {
                    **d1,  # Include all fields from d1
                    priceChange: [_priceChange],
                    createdAt: time(),
                }
            },
            upsert=True
                )
            )
        print("process ", _url)
    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print('Utills error')
        print(_url)
        print("Exception type: ", exception_type)
        print("exception_object: ", exception_object)
        print("Line number: ", line_number)
        errorInsert(_url,exception_type,exception_object,line_number,"Utills Error")


def bulkUpdate(bulk_operations, data,_pharmacyname,_url,_pharmacyStoreId,_category,_product,_price,_cutPrice,_img,_ingrads,_description,_presentation, _country=None, _marca=None, _originalPrice=0, _originalPriceCurrency=None, _managerPublicName=None, _speciality=None, _extraInfo = None, _provider = None, _extra = None, _title = None, _questionAnswers = None, _rating = None, _reviews = None, _accordions = None, _subtitle = None, _especialidad = None, _query = None, _countryOrigin = None, _conversionRate =None):
    try:
        if _country==None:
            _country="Mexico"
        if _marca==None:
            _marca=''
        if _price==None or _price=='' or _price==0 or _price == outOfStock:
            _price='0'
            _amount=0
            _outOfStock=True 
        else:
            _amount=float(_price.replace(",",'').replace('$','').replace('Q',''))
            _outOfStock=False

        if data["amount"] < _amount: 
            notifyPriceChangeRequest(str(data["_id"]))

        _priceChange=data[priceChange]
        _priceChange.append({tPrice:_amount,date:time()})
        d1={
            pharmacyName:_pharmacyname,
            pharmacyStoreId:_pharmacyStoreId,
            category:_category,
            product:_product,
            normalizedName : unidecode.unidecode(_product),
            price:_price,
            outOfStock:_outOfStock,
            cutPrice:_cutPrice,
            image:_img,
            amount:_amount,
            updatedAt:time(),
            country:_country,
            marca:_marca,
            speciality : _speciality,
            extraInfo:{ 
            ingredientes:_ingrads,
            description:_description,
            presentation:_presentation,
            originalPriceCurrency:_originalPriceCurrency,
            originalPrice:_originalPrice
                },
            categorySlug:get_cleaned_cat(_category, categorySlug),
            medicineSlug:get_cleaned_cat(_product, medicineSlug),
            pharmacyNameSlug:get_cleaned_cat(_pharmacyname, pharmacyNameSlug),
            priceChange:_priceChange,
            isDeleted : False,
            managerPublicName :_managerPublicName,
            provider : _provider,
            title :_title,
            questionAnswers : _questionAnswers,
            rating : _rating,
            reviews : _reviews,
            accordions : _accordions,
            subtitle : _subtitle,
            countryOrigin : _countryOrigin,
            originCountry : _countryOrigin,
            scrapped: True
            }
        if createdAt not in data:
            d1.update({createdAt:time()})
        if _extraInfo:
            d1.update(_extraInfo)
        if _extra:
            d1.update(_extra)
        _priceChange = {price: _amount, date: time(), originalPrice:float(_originalPrice), conversionRate:_conversionRate, originalPriceCurrency:_originalPriceCurrency}
        if _query:
            bulk_operations.append(
                UpdateOne(
                    _query,  # Filter: find by URL
                    {
                    "$push": {
                        priceChange: _priceChange  # Append the new price to priceChange array
                        },
                    "$set": d1  # Update or insert the data
                    },
                    upsert=True  # Insert if not found
                )
            )
        else:
            bulk_operations.append(
                UpdateOne(
                    {url: _url},  # Filter: find by URL
                    {"$set": d1},  # Update or insert the data
                    upsert=True  # Insert if not found
                )
            )
        itemCount(_pharmacyname, _country, "update")
        print("update", _url)
    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print('Utills error')
        print(_url)
        print("Exception type: ", exception_type)
        print("exception_object: ", exception_object)
        print("Line number: ", line_number)
        errorInsert(_url,exception_type,exception_object,line_number,"Utills Error")

def nahdionlineBulkInsert(bulk_operations, _pharmacyname, _url, _pharmacyStoreId, _category, _product, _price, _cutPrice, _img, _ingrads, _description, _presentation, _country=None, _marca=None, _originalPrice=0, _originalPriceCurrency=None, _managerPublicName=None, _speciality=None, _extraInfo=None, _provider=None, _extra=None, _title=None, _questionAnswers=None, _rating=None, _reviews=None, _accordions=None, _subtitle=None, _especialidad=None, _query=None, _countryOrigin=None, _conversionRate=None):
    try:
        if _country == None:
            _country = "Mexico"
        if _marca == None:
            _marca = ''
        if _price == None or _price == '' or _price == 0 or _price == outOfStock:
            _price = '0'
            _amount = 0
            _outOfStock = True
        else:
            _amount = float(_price.replace(
                ",", '').replace('$', '').replace('Q', ''))
            _outOfStock = False

        d1 = {
            pharmacyName: _pharmacyname,  # string
            url: _url,  # string
            pharmacyStoreId: _pharmacyStoreId,  # string
            category: _category,  # string
            product: _product,  # string
            normalizedName: unidecode.unidecode(_product),
            price: _price,  # string
            outOfStock: _outOfStock,
            cutPrice: _cutPrice,  # string
            image: _img,  # list
            amount: _amount,  # int
            # createdAt:time(),
            updatedAt: time(),
            country: _country,  # string
            marca: _marca,  # string
            speciality: _speciality,  # list
            extraInfo: {
                ingredientes: _ingrads,  # list
                description: _description,  # string
                presentation: _presentation,  # string
                originalPriceCurrency: _originalPriceCurrency,  # string
                originalPrice: _originalPrice  # string
            },
            categorySlug: get_cleaned_cat(_category, categorySlug),
            medicineSlug: get_cleaned_cat(_product, medicineSlug),
            pharmacyNameSlug: get_cleaned_cat(_pharmacyname, pharmacyNameSlug),
            # priceChange:[{tPrice:_amount,date:time()}],
            isDeleted: False,
            managerPublicName: _managerPublicName,
            provider: _provider,
            title: _title,
            questionAnswers: _questionAnswers,
            rating: _rating,
            reviews: _reviews,
            accordions: _accordions,
            subtitle: _subtitle,
            countryOrigin: _countryOrigin,
            originCountry: _countryOrigin,
            scrapped: True
        }
        if _extraInfo:
            d1.update(_extraInfo)
        if _extra:
            d1.update(_extra)

        if not _query:
            _query = {url: _url}

        _priceChange = {price: _amount, date: time(), originalPrice: float(
            _originalPrice), conversionRate: _conversionRate, originalPriceCurrency: _originalPriceCurrency}

        # Single upsert operation that handles both insert and update cases correctly
        bulk_operations.append(UpdateOne(
            _query,
            {
                "$set": d1,  # This will always set isDeleted: False and update all fields
                "$push": {
                    priceChange: _priceChange
                },
                "$setOnInsert": {
                    createdAt: time(),
                }
            },
            upsert=True
        )
        )
        print("process ", _url)
    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print('Utills error')
        print(_url)
        print("Exception type: ", exception_type)
        print("exception_object: ", exception_object)
        print("Line number: ", line_number)
        errorInsert(_url, exception_type, exception_object,
                    line_number, "Utills Error")


def updateScrapperFalse(pharmacyname):
    try:
        collection = db['pharmacies']
        collection.update_many({pharmacyName:pharmacyname}, {"$set":{scrapped:False}})
    except Exception as e:
        print("error ",e)

def updateIsDeletedTrue(pharmacyname):
    try:
        collection = db['pharmacies']
        collection.update_many({pharmacyName:pharmacyname,scrapped:False}, {"$set":{isDeleted:True}})
    except Exception as e:
        print("error ", e)