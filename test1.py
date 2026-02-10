from flask import Flask
from crypto import return_app_route, load_pri
app = Flask(__name__)

path = input("输入私钥的绝对路径")
pri = load_pri(path)

api = return_app_route(app, pri)

@api('/', methods=['POST'])
def func(req):
    if req == {}:
        print("Wrong request")
        return "Wrong requests!"
    print(req)
    return "Hello World"

app.run()