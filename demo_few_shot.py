"""Demo script showcasing few-shot prompting capabilities."""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from llm.langchain_prompts import FewShotSQLPromptManager
from database import DatabaseConnection
from config import DATABASE_CONFIG

def demo_few_shot_prompting():
    """Demonstrate few-shot prompting capabilities."""
    
    print("🎯 Few-Shot SQL Prompting Demo")
    print("=" * 50)
    
    # Initialize components
    try:
        prompt_manager = FewShotSQLPromptManager()
        db_connection = DatabaseConnection(DATABASE_CONFIG['path'])
        schema_info = db_connection.get_schema_info()
        
        print("✅ Components initialized successfully!")
        print(f"📊 Database: {db_connection.db_type}")
        print(f"📝 Few-shot examples loaded: {len(prompt_manager.examples)}")
        
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        return
    
    print("\n" + "="*50)
    
    # Demo queries
    demo_queries = [
        "Show me all artists",
        "How many tracks are there?", 
        "Find customers from Canada",
        "Get the most expensive track",
        "List albums with their artists",
        "Count employees by title",
        "Show recent invoices",
        "Find rock music tracks"
    ]
    
    print("🔍 Testing Few-Shot Prompt Generation")
    print("-" * 50)
    
    for i, query in enumerate(demo_queries, 1):
        print(f"\n{i}. Query: '{query}'")
        print("-" * 30)
        
        try:
            # Get similar examples
            similar_examples = prompt_manager.get_similar_examples(query, k=3)
            
            print("🎯 Similar Examples Found:")
            for j, example in enumerate(similar_examples, 1):
                print(f"   {j}. {example['input']} -> {example['query']}")
            
            # Generate few-shot prompt
            prompt = prompt_manager.build_few_shot_sql_prompt(
                query, 
                str(schema_info),
                num_examples=3
            )
            
            print(f"\n📝 Generated Few-Shot Prompt (first 200 chars):")
            print(f"   {prompt[:200]}...")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n" + "="*50)
    
    # Interactive demo
    print("🎮 Interactive Few-Shot Demo")
    print("Type queries to see few-shot prompts (type 'quit' to exit)")
    print("-" * 50)
    
    while True:
        try:
            user_query = input("\n📝 Enter your query: ").strip()
            
            if user_query.lower() == 'quit':
                break
            
            if not user_query:
                continue
            
            # Show similar examples
            similar = prompt_manager.get_similar_examples(user_query, k=5)
            
            print(f"\n🎯 Top {len(similar)} Similar Examples:")
            for i, ex in enumerate(similar, 1):
                print(f"   {i}. {ex['input']}")
                print(f"      SQL: {ex['query']}")
            
            # Generate and show prompt
            prompt = prompt_manager.build_few_shot_sql_prompt(
                user_query,
                str(schema_info),
                num_examples=3
            )
            
            print(f"\n📄 Complete Few-Shot Prompt:")
            print("=" * 40)
            print(prompt)
            print("=" * 40)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n👋 Demo completed!")


def demo_example_management():
    """Demonstrate dynamic example management."""
    
    print("\n🔧 Example Management Demo")
    print("=" * 50)
    
    try:
        prompt_manager = FewShotSQLPromptManager()
        
        print(f"📊 Initial examples: {len(prompt_manager.examples)}")
        
        # Add new examples
        new_examples = [
            ("Show top selling albums", "SELECT Album.Title, SUM(InvoiceLine.Quantity) as Sales FROM Album JOIN Track ON Album.AlbumId = Track.AlbumId JOIN InvoiceLine ON Track.TrackId = InvoiceLine.TrackId GROUP BY Album.Title ORDER BY Sales DESC LIMIT 10;"),
            ("Find jazz artists", "SELECT DISTINCT Artist.Name FROM Artist JOIN Album ON Artist.ArtistId = Album.ArtistId JOIN Track ON Album.AlbumId = Track.AlbumId JOIN Genre ON Track.GenreId = Genre.GenreId WHERE Genre.Name = 'Jazz';"),
            ("Customer purchase history", "SELECT Customer.FirstName, Customer.LastName, COUNT(Invoice.InvoiceId) as PurchaseCount FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId ORDER BY PurchaseCount DESC;")
        ]
        
        print("\n➕ Adding new examples:")
        for nl, sql in new_examples:
            prompt_manager.add_example(nl, sql)
            print(f"   ✅ Added: '{nl}'")
        
        print(f"\n📊 Updated examples: {len(prompt_manager.examples)}")
        
        # Test similarity with new examples
        test_query = "Show bestselling music"
        similar = prompt_manager.get_similar_examples(test_query, k=3)
        
        print(f"\n🎯 Similar examples for '{test_query}':")
        for i, ex in enumerate(similar, 1):
            print(f"   {i}. {ex['input']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def demo_query_types():
    """Demonstrate different query types with few-shot prompting."""
    
    print("\n📊 Query Types Demo")
    print("=" * 50)
    
    query_categories = {
        "Basic Queries": [
            "Show all genres",
            "List all playlists",
            "Display all media types"
        ],
        "Aggregation Queries": [
            "Average album price",
            "Total number of tracks per genre", 
            "Sum of all invoice totals"
        ],
        "Join Queries": [
            "Artists and their albums",
            "Customers and their orders",
            "Tracks with their genres"
        ],
        "Complex Queries": [
            "Most popular artist by sales",
            "Customers who bought rock music",
            "Employees with most sales"
        ]
    }
    
    try:
        prompt_manager = FewShotSQLPromptManager()
        db_connection = DatabaseConnection(DATABASE_CONFIG['path'])
        schema_info = db_connection.get_schema_info()
        
        for category, queries in query_categories.items():
            print(f"\n🏷️  {category}")
            print("-" * 30)
            
            for query in queries:
                similar = prompt_manager.get_similar_examples(query, k=2)
                print(f"   Query: {query}")
                print(f"   Best match: {similar[0]['input'] if similar else 'No match'}")
                print()
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("🚀 Starting Few-Shot Prompting Demos")
    print("=" * 60)
    
    # Run all demos
    demo_few_shot_prompting()
    demo_example_management() 
    demo_query_types()
    
    print("\n🎉 All demos completed!")
    print("\nTo run the enhanced bot with few-shot prompting:")
    print("   python main_langchain.py") 