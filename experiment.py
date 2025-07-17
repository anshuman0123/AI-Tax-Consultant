from google import genai
from pprint import pprint
from pinecone import Pinecone
# client = genai.Client(api_key="AIzaSyAZ7dtvfCTX0X8V6Qfaxi6TN_VQ9rCM9wo")

# response = client.models.generate_content_stream(
#     model="gemini-2.5-flash",
#     contents=["explain the events regarding 1975 emergency in India in brief"],
# )
# for chunk in response:
#     print(chunk.text, end="")
from google.genai import types

client = genai.Client(api_key="AIzaSyAZ7dtvfCTX0X8V6Qfaxi6TN_VQ9rCM9wo")

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
    from pinecone import Pinecone
    pc = Pinecone(api_key="pcsk_6vNZC9_BSAwXcKEzWvsT4LnvANDHxaUcpD7ENiUUQjX6PRPZDqYroAomH9poByvykEm4tP")
    index = pc.Index(host="https://uapalaw-pe84aca.svc.aped-4627-b74a.pinecone.io")
    results = index.search(
        namespace="income_tax_act_1961", 
        query={
            "inputs": {"text": question}, 
            "top_k": 3
        },
    )
    return results
tools = types.Tool(function_declarations=[pinecone_db_calling_function])
config = types.GenerateContentConfig(tools=[tools],system_instruction="""You are an assistant that can answer user queries.
Use the `db_calling` tool ONLY if the user's query is about the Indian Income Tax Act 1961 or related Indian tax laws.
For all other types of queries, answer using your own knowledge.
DO NOT use the tool for historical, political, or general knowledge topics.""")


chat = client.chats.create(model="gemini-2.5-flash",config=config)

# print(help(chat))

while True:
    prompt = input("\nenter prompt: \n")
    if prompt.lower() == "exit":
        break
    response = chat.send_message_stream(prompt)
    try:
        print("Response received, checking for tool calls...")
        # response.candidates[0].content.parts[0].function_call
        # Extract tool call details, it may not be in the first part.
        tool_call = response.candidates[0].content.parts[0].function_call
        print("Tool call found:", tool_call)
        if tool_call.name == "db_calling":
            print("Tool call detected:", tool_call)
            result = db_calling(**tool_call.args)
            response = chat.send_message_stream(
                message = prompt,
                config=types.GenerateContentConfig(
                    tools=types.Tool(function_declarations=[pinecone_db_calling_function]),
                )
            )
            for chunk in response:
                print(chunk.text, end="")

    except AttributeError:      
        for chunk in response:
            print(chunk.text, end="")

print("thanks")


# I need some help in saving taxes , I earn 10 lakhs per month pre taxation . what's the highest can I save