import httpx

r = httpx.get("http://localhost:8000/api/incidents?limit=100")
data = r.json()
print("TOTAL:", data["total"])
items = data["items"][::-1] # chronological ASC
for i, item in enumerate(items, 1):
    msg = str(item.get("exception_message", "")).replace("\n", " ")[:35]
    print(f"{i:2d} | {item['id']} | {item['detected_at']} | {item['exception_type']} | {msg} | in_flight: {item['in_flight_run_ids']}")
