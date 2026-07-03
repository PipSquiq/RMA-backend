# src/rma/integration.py
import asyncio
import httpx
from src.utils.db import db

async def trigger_external_customer_ticket(rma_id: str, rma_number: str, faulty_sn: str):
    """
    Worker yang berjalan di background untuk menembak API Customer System.
    Mensimulasikan integrasi otomatis sesuai dokumen PDF Ericsson.
    """
    print(f"🔄 [Background Task] Memulai integrasi tiket untuk {rma_number}...")
    
    # Simulasi payload yang dikirim ke sistem pelanggan
    payload = {
        "external_rma_reference": rma_id,
        "rma_code": rma_number,
        "issue_category": "Hardware Replacement",
        "faulty_device_sn": faulty_sn,
        "notes": "Automated ticket created via Ericsson RMA Value Added Flow Integration."
    }
    
    # Menggunakan httpx untuk simulasi call API eksternal
    try:
        # Kita simulasikan delay jaringan internet selama 3 detik
        await asyncio.sleep(3)
        
        # MOCKING: Anggap saja kita menembak ke https://api.customer.com/v1/tickets
        # Di dunia nyata kodenya: 
        # async with httpx.AsyncClient() as client:
        #     response = await client.post("https://api.customer.com/v1/tickets", json=payload)
        
        # Simulasi response sukses dari pihak customer
        mock_customer_ticket_id = f"TKT-CUST-{rma_number.split('-')[-1]}"
        print(f"✅ [Background Task] Tiket berhasil dibuat di Customer System: {mock_customer_ticket_id}")
        
        # Update rma_request di Neon DB dengan ID tiket eksternal tersebut
        await db.rma_request.update(
            where={"id": rma_id},
            data={"customer_ticket_id": mock_customer_ticket_id}
        )
        print(f"💾 [Background Task] Database sukses diperbarui dengan Customer Ticket ID.")
        
    except Exception as e:
        print(f"❌ [Background Task] Gagal mengintegrasikan tiket ke Customer System: {str(e)}")