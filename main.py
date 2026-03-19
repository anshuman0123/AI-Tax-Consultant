from fastapi import FastAPI, Body , Depends,Request , Header
from typing import Annotated
from google.oauth2 import id_token
from pydantic import BaseModel
from google.auth.transport import requests
from fastapi.responses import JSONResponse , HTMLResponse
import base64
import json
from fastapi import FastAPI, Form, HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.genai import types
from pinecone import Pinecone
import jwt
import asyncio
from pymongo import MongoClient

import requests
import os

mongoclient = MongoClient("mongodb://localhost:27017/")
db = mongoclient["taxassist_user"]
collection = db["userdetails"]

payment_confo = asyncio.Future()

# Initialize a Pinecone client with your API key
pc = Pinecone(api_key="Your_Pine_Cone_API_KEY")

app = FastAPI()
from google import genai

client = genai.Client(api_key="Your_genai_api_key")
chat = client.chats.create(model="gemini-2.5-flash")
chats = []


app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:5500"],  # Or specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

def decode_jwt_response(token):
    base64_url = token.split('.')[1]
    
    # Fix padding issue
    padding = '=' * (-len(base64_url) % 4)
    base64_url += padding
    
    # Decode base64url
    decoded_bytes = base64.urlsafe_b64decode(base64_url)
    json_payload = decoded_bytes.decode('utf-8')
    
    return json.loads(json_payload)

class Credential(BaseModel):
    credential: str

class Question(BaseModel):
    question: str

import os
from dodopayments import DodoPayments


# print(os.environ.get("DODO_PAYMENTS_API_KEY"))


dodoclient = DodoPayments(
    bearer_token=os.environ.get("DODO_PAYMENTS_API_KEY"), 
    environment="test_mode" # This is the default and can be omitted
)

# 7jpSvZnJw13hKfge.ClUQk1uacEdU_OQzitclPYCWBfGrJXdGfvnlZygAiJ-4OmaW

# app = FastAPI()
# WEB_CLIENT_ID = "482767827533-lqvp2m57si3m5j1ool7u2t9k469d0lgj.apps.googleusercontent.com"


# app = FastAPI()

GOOGLE_CLIENT_ID = "482767827533-lqvp2m57si3m5j1ool7u2t9k469d0lgj.apps.googleusercontent.com"
def auth_and_sub_checks(request: Request):
    cookies = request.cookies
    if not cookies:
        return "not logged in"
    user_details = collection.find_one({"google_id":jwt.decode(cookies["user_id"], "7a7439e040125556cb0800c2ee198db02cc310fa09771cc561898da40ad7b7c5", algorithms=['HS256'])['id']})
    if user_details['subscribed_till'] == "not subscribed":
        return "not subscribed"
    else:
        return "Subscribed"

@app.get("/")
async def root(check_auth = Depends(auth_and_sub_checks)):
    if check_auth == "not logged in":
        return JSONResponse(content={"status":"not logged in"})
    elif check_auth == "not subscribed":
        return JSONResponse(content={"status":"not subscribed"})
    else:
        return JSONResponse(content={"status":"subscribed"})
    
@app.post("/new_chat")
async def func(req : Request):
    global chat
    global chats
    collection.update_one({"google_id":jwt.decode(req.cookies["user_id"],"7a7439e040125556cb0800c2ee198db02cc310fa09771cc561898da40ad7b7c5",algorithms=['HS256'])['id']},{"$set":{"chats":chats}})
    chat = client.chats.create(model="gemini-2.5-flash")
    chats = []
    return JSONResponse(content={"message": "New chat started"})
@app.get("/payment_status")
async def func2(req : Request):
    global payment_confo
    payment_id = req.query_params.get("payment_id")
    status = req.query_params.get("status")
    # verify if the payment id is with latest payment

    payment = dodoclient.payments.retrieve(
        payment_id=payment_id,
    )
    print(payment.brand_id)
    if not payment_confo.done():
        payment_confo.set_result(str(payment.status))
    # print(payment.brand_id)
    return HTMLResponse(content=f"""
    <html>
        <head>
            <title></title>
        </head>
        <body>
            <h1 id="status">Payment status loading</h1>
            <h1 id="m"></h1>
            <script>
                // Simulate fetching payment status 
                setTimeout(() => {{
                    document.getElementById("status").innerText = "Payment status: {payment.status}";
                    document.getElementById("m").innerText = "Close this window to continue using the app";
                }}, 3000);                   
            </script>        
        </body>
    </html>                    

""")

from fastapi.responses import JSONResponse
import json

@app.get("/create_payment")
async def dijij(req: Request):
    global payment_confo
    payment_confo = asyncio.Future()
    async def create_payment():
        print("inside create payment")
        payment = dodoclient.payments.create(
            payment_link=True,
            billing={
                "city": "bhadrak",
                "country": "IN",
                "state": "ODISHA",
                "street": "salandi bypass",
                "zipcode": "756100",
            },
            customer={
                "customer_id": "cus_gYFZXyj9L0lRejqVDh1qz"
            },
            product_cart=[{
                "product_id": "pdt_kL3kYuIFX9BtmYMFmSgqJ",
                "quantity": 1,
            }],
            return_url="https://localhost/api/payment_status",
        )
        # print(payment.to_dict())
        # yield str(payment.to_dict())
        yield  f"data: {json.dumps({'message': 'payment init', 'payment_link': payment.payment_link})}\n\n"
        await payment_confo
        yield f"data: {json.dumps({'message': 'payment result','status':payment_confo.result()})}\n\n"
    
    return StreamingResponse(create_payment(), media_type="text/event-stream")
    

@app.post("/login")
async def login_with_google(credential: Credential):
    try:
        # Verify the token
        # idinfo = id_token.verify_oauth2_token(
        #     credential,
        #     requests.Request(),
        #     GOOGLE_CLIENT_ID
        # )
        idinfo = decode_jwt_response(credential.credential)
        
        # Extract user info
        user_id = idinfo["sub"]
        email = idinfo["email"]
        name = idinfo.get("name")
        picture = idinfo.get("picture")

        user_info = {
                "id": user_id,
                "email": email,
                "name": name,
                "picture": picture
        }
        collection.insert_one({
            "google_id": user_id,
            "email": email, 
            "name": name,
            "picture": picture,
            "phonenumber":"hehe",
            "chats": [],
            "subscribed_till":"not subscribed",
            "number_of_subs":0,
        })  # Save user info to MongoDB
        user_info = jwt.encode(user_info,"7a7439e040125556cb0800c2ee198db02cc310fa09771cc561898da40ad7b7c5",algorithm="HS256")
        response = JSONResponse(content={"message": "Login successful"})
        response.set_cookie(
            key="user_id",
            value=user_info,
            samesite="none",
            secure=True,
            max_age=30 * 24 * 60 * 60,  # 30 days in seconds
            domain="localhost",  # Adjust domain as needed
            httponly=True,  # Prevents JavaScript access to the cookie
        )
        # You can now create/retrieve the user from DB, issue your own JWT, etc.
        return response


    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")

pinecone_db_calling_function = {
    "name": "db_calling",
    "description": "Use this function **only** when the question is about the Income Tax Act 1961 or related Indian tax law topics. Do not use for historical, political, or unrelated topics.",
    "parameters": { 
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "A query strictly related to Indian Income Tax Act 1961",
            }
        },
        "required": ["question"]
    }
}

def db_calling(question: str):
    # index = pc.Index(host="https://uapalaw-pe84aca.svc.aped-4627-b74a.pinecone.io")
    # results = index.search(
    #     namespace="income_tax_act_1961", 
    #     query={
    #         "inputs": {"text": question}, 
    #         "top_k": 4
    #     },
    # )
    # return results
    INDEX_HOST = os.getenv("INDEX_HOST", "uapalaw-pe84aca.svc.aped-4627-b74a.pinecone.io")  # From your error
    NAMESPACE = os.getenv("NAMESPACE", "income_tax_act_1961")
    url = f"https://{INDEX_HOST}/records/namespaces/{NAMESPACE}/search"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Api-Key": "pcsk_6vNZC9_BSAwXcKEzWvsT4LnvANDHxaUcpD7ENiUUQjX6PRPZDqYroAomH9poByvykEm4tP" ,
        "X-Pinecone-API-Version": "unstable"
    }
    payload = {
        "query": {
            "inputs": {"text": question},
            "top_k": 4
        },
    }
    response = requests.post(url, json=payload, headers=headers, verify=False)
    return response.text
    
    # tools = types.Tool(function_declarations=[pinecone_db_calling_function])
# config = types.GenerateContentConfig(tools=[tools],system_instruction="""You are an assistant that can answer user queries.
# Use the `db_calling` tool ONLY if the user's query is about the Indian Income Tax Act 1961 or related Indian tax laws.
# For all other types of queries, answer using your own knowledge.
# DO NOT use the tool for historical, political, or general knowledge topics.""")



temp = ""

@app.get("/answer")
async def answer(req : Request , check_auth = Depends(auth_and_sub_checks)):
    chats.append({"role":"user","message":req.headers["question"]})
    def infunc():
        #print("inside infunc")
        global temp
        pre_response = client.models.generate_content(model="gemini-2.5-flash",contents=f" here is the question : {req.headers["question"]} , based on this tell me is this function needed to be called or not {pinecone_db_calling_function} return either True or False nothing else")
        # print(pre_response.text)
        print(pre_response)
        if pre_response.text == "True":
            print("function calling triggered")
            func_response = db_calling(req.headers["question"])
            print(func_response)
            from pypdf import PdfReader
            reader = PdfReader("C:/Users/ANROUT0/Downloads/Finance_Bill.pdf")
            all_text = ""
            for page in reader.pages:
                all_text += page.extract_text()
            response = chat.send_message_stream(req.headers["question"]+ f"context (relevant sections of Income Tax act 1961): {func_response} and finance bill 2025 as a whole : {all_text}")
            # print("google_id", jwt.decode(req.cookies["user_id"],"7a7439e040125556cb0800c2ee198db02cc310fa09771cc561898da40ad7b7c5",algorithm="HS256")["id"])
            for chunk in response:
                temp+=chunk.text+' '
                yield chunk.text.encode('utf-8')
        else:
            response = chat.send_message_stream(req.headers["question"])
            for chunk in response:
                temp+=chunk.text+' '
                yield chunk.text.encode('utf-8')
        global chats
        chats.append({"role":"AI","message":temp})
        temp = ''
    
    return StreamingResponse(infunc(), media_type="text/plain")
   
    


# https://test.dodopayments.com/payments
    
