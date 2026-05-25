from fastapi import APIRouter
from collections import defaultdict
from services.vector_store import get_vector_store_service

router = APIRouter()

@router.get("/")
async def get_documents():

    try:
        vector_store = get_vector_store_service()

        chunks = vector_store.get_all_documents()

        docs_map = defaultdict(
            lambda: {
                "doc_id": "",
                "filename": "",
                "total_pages": 0,
                "chunk_count": 0,
                "ocr_applied": False,
                "upload_timestamp": ""
            }
        )

        for chunk in chunks:

            doc_id = chunk.get("doc_id")
            metadata = chunk.get("metadata", {})

            docs_map[doc_id]["doc_id"] = doc_id
            docs_map[doc_id]["filename"] = chunk.get(
                "filename",
                "unknown"
            )

            docs_map[doc_id]["chunk_count"] += 1

            page = chunk.get("page_num",0)

            docs_map[doc_id]["total_pages"] = max(
                docs_map[doc_id]["total_pages"],
                page
            )

            docs_map[doc_id]["ocr_applied"] = metadata.get(
                "ocr_applied",
                False
            )

            docs_map[doc_id]["upload_timestamp"] = metadata.get(
                "upload_timestamp",
                ""
            )

        documents = list(docs_map.values())

        return {
            "documents": documents,
            "total": len(documents)
        }

    except Exception as e:
        return {
            "documents": [],
            "total": 0,
            "error": str(e)
        }