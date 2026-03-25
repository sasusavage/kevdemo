import os
from groq import Groq
from flask import current_app
import services

def get_ai_context():
    """
    Produce a high-density summary of the current inventory state for the AI Brain.
    """
    stats = services.get_sales_stats()
    forecasts = services.get_forecast()
    distributors = services.get_distributor_performance()
    
    # Filter for urgent items
    critical_items = [f for f in forecasts if f['alert_level'] == 'critical']
    low_stock = [f for f in forecasts if f['alert_level'] == 'warning']
    
    # Top distributors
    top_dist = sorted(distributors, key=lambda x: x['total_revenue'], reverse=True)[:3]
    
    context = f"""
    --- SYSTEM SNAPSHOT ---
    Total Units Sold (Lifetime): {stats['total_sales_volume']}
    Total Lifetime Revenue: GHC {stats['total_revenue']}
    
    INVENTORY STATUS:
    - Critical Items (ACTION REQUIRED): {len(critical_items)} 
    - Low Stock: {len(low_stock)}
    
    TOP DISTRIBUTOR PERFORMANCE:
    """
    for d in top_dist:
        context += f"- {d['name']} ({d['tier']}): {d['total_revenue']} revenue\n"
        
    return context.strip()

def ask_ai_brain(user_query: str):
    """
    Generate insights using the Groq client.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Brain is offline. Please set GROQ_API_KEY in your .env configuration."
        
    data_context = get_ai_context()
    
    system_prompt = (
        "You are the 'Brain' of Prism Portal, an AI-powered inventory ERP. "
        "Use the following real-time data to help the user manage their inventory. "
        "Be concise, analytical, and prioritize profit maximization.\n\n"
        f"CONTEXT:\n{data_context}"
    )

    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            messages=[
              {"role": "system", "content": system_prompt},
              {"role": "user", "content": user_query}
            ],
            temperature=0.7,
            max_tokens=2048,
            top_p=1,
            stream=False
        )
        return completion.choices[0].message.content
        
    except Exception as e:
        return f"Brain Error: {str(e)}"
