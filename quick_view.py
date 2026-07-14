# quick_view.py
from app.config import settings
import chromadb

client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_PATH)

print("="*60)
print("ChromaDB 数据概览")
print("="*60)

for name in ["copies", "hotlist_topics", "user_documents"]:
    try:
        coll = client.get_collection(name)
        count = coll.count()
        print(f"\n✅ {name}: {count} 条记录")
        
        if count > 0:
            sample = coll.get(limit=1)
            print(f"   示例标题: {sample['metadatas'][0].get('title', 'N/A')}")
            print(f"   示例内容: {sample['documents'][0][:50]}...")
    except Exception as e:
        print(f"\n❌ {name}: 不存在或错误 - {e}")

print("\n" + "="*60)