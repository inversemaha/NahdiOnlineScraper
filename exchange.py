import requests

def Panama_to_Mexico_rate(): 
    panama_to_mexico=str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=PAB&to=MXN&amount=1').json()['result'])
    return panama_to_mexico
   
def Bolivia_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=BOB&to=MXN&amount=1').json()['result'])

def Colombia_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=COP&to=MXN&amount=1').json()['result'])

def Guatemala_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=GTQ&to=MXN&amount=1').json()['result'])

def Costa_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=CRC&to=MXN&amount=1').json()['result'])

def Nicaragua_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=NIO&to=MXN&amount=1').json()['result'])

def Salvador_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=SVC&to=MXN&amount=1').json()['result'])

def Dominicana_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=DOP&to=MXN&amount=1').json()['result'])

def Honduras_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=HNL&to=MXN&amount=1').json()['result'])

def India_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=INR&to=MXN&amount=1').json()['result'])

def USA_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=USD&to=MXN&amount=1').json()['result'])

def Venezuela_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=VES&to=MXN&amount=1').json()['result'])

def Turkey_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=TRY&to=MXN&amount=1').json()['result'])

def Saudia_to_Mexico_rate():
    return str(requests.get('https://api.exchangeratesapi.io/v1/convert?access_key=36f7810dfb9321e6f169ea28682c25e9&from=SAR&to=MXN&amount=1').json()['result'])
