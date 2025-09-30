from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.parser import FileParser
from app.models.transaction import Transaction
from datetime import datetime

router = APIRouter()

@router.post("/parse-transactions")
async def parse_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    parser = FileParser(file)
    parsed_data = await parser.parse()
    
    # Heuristic-based mapping of parsed data to the Transaction model
    # This will likely need to be improved with a more robust mapping strategy.
    transactions_to_create = []
    for item in parsed_data:
        # This is a very basic and brittle mapping. 
        # It assumes keys like 'Transaction Date', 'Amount', 'Description', etc.
        # A more robust solution would involve a schema mapping layer.
        try:
            transaction_date_str = item.get("Transaction Date") or item.get("date") or item.get("Date")
            amount_str = item.get("Amount") or item.get("amount")
            
            if transaction_date_str and amount_str:
                transaction_date = datetime.strptime(transaction_date_str, "%Y-%m-%d") # Assuming "YYYY-MM-DD" format
                amount = float(str(amount_str).replace("$","").replace(",",""))

                new_transaction = Transaction(
                    transaction_date=transaction_date,
                    amount=amount,
                    source=item.get("Source") or item.get("source"),
                    notes=item.get("Description") or item.get("notes") or item.get("description")
                )
                transactions_to_create.append(new_transaction)
        except (ValueError, TypeError) as e:
            # Skip records that can't be parsed into the required types
            print(f"Skipping record due to parsing error: {item} - Error: {e}")
            continue

    if not transactions_to_create:
        raise HTTPException(status_code=400, detail="No valid transactions could be parsed from the file.")

    try:
        db.add_all(transactions_to_create)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save transactions to the database: {e}")

    return {"filename": file.filename, "transactions_saved": len(transactions_to_create)}

@router.get("/transactions")
def get_transactions(db: Session = Depends(get_db)):
    return db.query(Transaction).all()
