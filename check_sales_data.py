from core.db import get_purchase_collection
from bson.objectid import ObjectId

purchase_col = get_purchase_collection()
sample_sales = list(purchase_col.find().limit(5))

print("--- Sample Sales ---")
for sale in sample_sales:
    print(f"ID: {sale['_id']}, branch_id: {sale.get('branch_id')} ({type(sale.get('branch_id'))}), date: {sale.get('date')}, timestamp: {sale.get('timestamp')}")
