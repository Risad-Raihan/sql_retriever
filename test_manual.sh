#!/bin/bash
# Manual Testing Script for SQL Retriever FastAPI
# Tests all endpoints with various scenarios including edge cases and error conditions

set -e  # Exit on error

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-test-api-key-12345}"
TEST_DB_PATH="${TEST_DB_PATH:-./data/test_crm_v1.db}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED_TESTS++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Test execution wrapper
run_test() {
    local test_name="$1"
    local expected_status="$2"
    shift 2
    
    ((TOTAL_TESTS++))
    log_info "Testing: $test_name"
    
    # Execute curl command and capture response
    response=$(curl -s -w "%{http_code}" "$@")
    http_code="${response: -3}"
    response_body="${response%???}"
    
    # Check status code
    if [[ "$http_code" == "$expected_status" ]]; then
        log_success "$test_name - Status: $http_code"
        if [[ -n "$response_body" && "$response_body" != "null" ]]; then
            echo "Response: $(echo "$response_body" | jq . 2>/dev/null || echo "$response_body")"
        fi
    else
        log_error "$test_name - Expected: $expected_status, Got: $http_code"
        echo "Response: $response_body"
    fi
    
    echo "---"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        log_warning "jq not found. JSON responses won't be formatted."
    fi
    
    # Check if server is running
    if ! curl -s "$API_BASE_URL/health" &> /dev/null; then
        log_error "Server not reachable at $API_BASE_URL"
        log_info "Please start the server first: uvicorn app:app --reload"
        exit 1
    fi
    
    log_success "Prerequisites check completed"
    echo "---"
}

# Test Root Endpoint
test_root() {
    log_info "=== Testing Root Endpoint ==="
    
    run_test "Root endpoint" "200" \
        -X GET "$API_BASE_URL/"
}

# Test Health Endpoint
test_health() {
    log_info "=== Testing Health Endpoint ==="
    
    run_test "Health check" "200" \
        -X GET "$API_BASE_URL/health"
}

# Test Query Endpoint
test_query() {
    log_info "=== Testing Query Endpoint ==="
    
    # Valid queries
    run_test "Simple count query" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "How many customers are there?"}'
    
    run_test "Customer list query" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "Show me all customers from USA"}'
    
    run_test "Revenue analysis query" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "What is the total revenue this year?"}'
    
    run_test "Product query" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "List top 5 products by price"}'
    
    # Query with database URI override
    run_test "Query with DB URI override" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d "{\"question\": \"Count customers\", \"db_uri\": \"sqlite:///$TEST_DB_PATH\"}"
    
    # Authentication tests
    run_test "Query without auth" "403" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -d '{"question": "How many customers?"}'
    
    run_test "Query with invalid auth" "401" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer invalid-key" \
        -d '{"question": "How many customers?"}'
    
    # Invalid input tests
    run_test "Query with empty question" "422" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": ""}'
    
    run_test "Query with missing question" "422" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{}'
    
    run_test "Query with too long question" "422" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d "{\"question\": \"$(printf 'x%.0s' {1..600})\"}"
    
    # Malformed JSON
    run_test "Query with malformed JSON" "422" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "test"'
}

# Test Schema Endpoint
test_schema() {
    log_info "=== Testing Schema Endpoint ==="
    
    run_test "Get schema" "200" \
        -X GET "$API_BASE_URL/schema" \
        -H "Authorization: Bearer $API_KEY"
    
    run_test "Get schema with DB URI" "200" \
        -X GET "$API_BASE_URL/schema?db_uri=sqlite:///$TEST_DB_PATH" \
        -H "Authorization: Bearer $API_KEY"
    
    run_test "Schema without auth" "403" \
        -X GET "$API_BASE_URL/schema"
    
    run_test "Schema with invalid auth" "401" \
        -X GET "$API_BASE_URL/schema" \
        -H "Authorization: Bearer invalid-key"
}

# Test Learn Endpoint
test_learn() {
    log_info "=== Testing Learn Endpoint ==="
    
    run_test "Learn from successful query" "200" \
        -X POST "$API_BASE_URL/learn" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{
            "question": "How many customers?",
            "sql_query": "SELECT COUNT(*) FROM customers;",
            "success": true,
            "feedback": "Query worked perfectly"
        }'
    
    run_test "Learn from failed query" "200" \
        -X POST "$API_BASE_URL/learn" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{
            "question": "Invalid query test",
            "sql_query": "SELECT * FROM nonexistent_table;",
            "success": false,
            "feedback": "Table does not exist"
        }'
    
    run_test "Learn without auth" "403" \
        -X POST "$API_BASE_URL/learn" \
        -H "Content-Type: application/json" \
        -d '{
            "question": "Test",
            "sql_query": "SELECT 1;",
            "success": true,
            "feedback": "Test"
        }'
    
    run_test "Learn with invalid input - empty question" "422" \
        -X POST "$API_BASE_URL/learn" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{
            "question": "",
            "sql_query": "SELECT 1;",
            "success": true,
            "feedback": "Test"
        }'
    
    run_test "Learn with missing fields" "422" \
        -X POST "$API_BASE_URL/learn" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{
            "question": "Test"
        }'
}

# Test Stats Endpoint
test_stats() {
    log_info "=== Testing Stats Endpoint ==="
    
    run_test "Get statistics" "200" \
        -X GET "$API_BASE_URL/stats" \
        -H "Authorization: Bearer $API_KEY"
    
    run_test "Stats without auth" "403" \
        -X GET "$API_BASE_URL/stats"
    
    run_test "Stats with invalid auth" "401" \
        -X GET "$API_BASE_URL/stats" \
        -H "Authorization: Bearer invalid-key"
}

# Test High Load Scenarios
test_load() {
    log_info "=== Testing Load Scenarios ==="
    
    # Concurrent requests
    log_info "Running 10 concurrent health check requests..."
    for i in {1..10}; do
        (curl -s "$API_BASE_URL/health" &)
    done
    wait
    log_success "Concurrent health checks completed"
    
    # Rapid fire requests
    log_info "Running 5 rapid query requests..."
    for i in {1..5}; do
        curl -s -X POST "$API_BASE_URL/query" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $API_KEY" \
            -d '{"question": "Count customers"}' &
    done
    wait
    log_success "Rapid queries completed"
}

# Test Edge Cases
test_edge_cases() {
    log_info "=== Testing Edge Cases ==="
    
    # Large request body (but within limits)
    large_question="What is the comprehensive analysis of customer behavior patterns including geographical distribution, purchasing trends, seasonal variations, product preferences, payment methods, and overall business performance metrics?"
    run_test "Large but valid question" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d "{\"question\": \"$large_question\"}"
    
    # Special characters in question
    run_test "Question with special characters" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "How many customers have names with àáâãäå characters?"}'
    
    # Unicode in question
    run_test "Question with unicode" "200" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "How many customers are from 中国 or España?"}'
    
    # Test with different content types
    run_test "Invalid content type" "422" \
        -X POST "$API_BASE_URL/query" \
        -H "Content-Type: text/plain" \
        -H "Authorization: Bearer $API_KEY" \
        -d "How many customers?"
}

# Performance testing
test_performance() {
    log_info "=== Testing Performance ==="
    
    # Time a simple query
    log_info "Timing simple query performance..."
    start_time=$(date +%s.%3N)
    
    response=$(curl -s -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "Count customers"}')
    
    end_time=$(date +%s.%3N)
    duration=$(echo "$end_time - $start_time" | bc -l)
    
    log_info "Query completed in ${duration}s"
    
    # Extract processing time from response
    if command -v jq &> /dev/null; then
        processing_time=$(echo "$response" | jq -r '.processing_time // "N/A"')
        log_info "Server reported processing time: ${processing_time}s"
    fi
}

# Generate summary report
generate_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="manual_test_report_$(date +%Y%m%d_%H%M%S).md"
    
    cat > "$report_file" << EOF
# Manual Test Report - SQL Retriever API

**Generated:** $timestamp  
**Base URL:** $API_BASE_URL  
**Total Tests:** $TOTAL_TESTS  
**Passed:** $PASSED_TESTS  
**Failed:** $FAILED_TESTS  
**Success Rate:** $(( PASSED_TESTS * 100 / TOTAL_TESTS ))%

## Test Results Summary

### Endpoint Coverage
- ✅ Root endpoint (/)
- ✅ Health endpoint (/health)
- ✅ Query endpoint (/query)
- ✅ Schema endpoint (/schema)
- ✅ Learn endpoint (/learn)
- ✅ Stats endpoint (/stats)

### Test Categories Covered
- ✅ Happy path scenarios
- ✅ Authentication tests
- ✅ Input validation
- ✅ Error handling
- ✅ Edge cases
- ✅ Load testing
- ✅ Performance testing

### Recommendations
EOF

    if [[ $FAILED_TESTS -gt 0 ]]; then
        echo "- 🔴 $FAILED_TESTS tests failed. Review server logs and fix issues before deployment." >> "$report_file"
    else
        echo "- ✅ All tests passed! API is ready for deployment." >> "$report_file"
    fi
    
    echo "- 📊 Review detailed logs above for specific test results." >> "$report_file"
    echo "- 🔧 Consider running automated test suite with: python test_runner.py" >> "$report_file"
    
    log_info "Test report saved to: $report_file"
}

# Main execution
main() {
    echo "🚀 SQL Retriever API Manual Testing Suite"
    echo "========================================"
    echo "Base URL: $API_BASE_URL"
    echo "API Key: ${API_KEY:0:10}..."
    echo "----------------------------------------"
    
    check_prerequisites
    
    # Run all test suites
    test_root
    test_health
    test_query
    test_schema
    test_learn
    test_stats
    test_load
    test_edge_cases
    test_performance
    
    # Generate summary
    echo "========================================"
    echo "📊 Test Summary"
    echo "========================================"
    echo "Total Tests: $TOTAL_TESTS"
    echo "Passed: $PASSED_TESTS"
    echo "Failed: $FAILED_TESTS"
    echo "Success Rate: $(( PASSED_TESTS * 100 / TOTAL_TESTS ))%"
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        log_success "All tests passed! 🎉"
    else
        log_error "$FAILED_TESTS tests failed. Review the output above."
    fi
    
    generate_report
    
    # Exit with appropriate code
    exit $FAILED_TESTS
}

# Script usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help          Show this help message"
    echo "  -u, --url URL       Set API base URL (default: http://localhost:8000)"
    echo "  -k, --key KEY       Set API key (default: test-api-key-12345)"
    echo "  -d, --db PATH       Set test database path (default: ./data/test_crm_v1.db)"
    echo "  -q, --quick         Run quick smoke tests only"
    echo ""
    echo "Environment variables:"
    echo "  API_BASE_URL        API base URL"
    echo "  API_KEY             API authentication key"
    echo "  TEST_DB_PATH        Test database file path"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run all tests with defaults"
    echo "  $0 -u http://localhost:8080          # Test different port"
    echo "  $0 -k my-secret-key                  # Use custom API key"
    echo "  $0 --quick                           # Run smoke tests only"
}

# Quick smoke test mode
quick_test() {
    log_info "Running quick smoke tests..."
    
    ((TOTAL_TESTS++))
    if curl -s "$API_BASE_URL/health" | grep -q "healthy\|status"; then
        log_success "Health check"
        ((PASSED_TESTS++))
    else
        log_error "Health check"
        ((FAILED_TESTS++))
    fi
    
    ((TOTAL_TESTS++))
    if curl -s -X POST "$API_BASE_URL/query" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{"question": "test"}' | grep -q "success\|sql_query"; then
        log_success "Query endpoint"
        ((PASSED_TESTS++))
    else
        log_error "Query endpoint"
        ((FAILED_TESTS++))
    fi
    
    echo "Quick test complete: $PASSED_TESTS/$TOTAL_TESTS passed"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -u|--url)
            API_BASE_URL="$2"
            shift 2
            ;;
        -k|--key)
            API_KEY="$2"
            shift 2
            ;;
        -d|--db)
            TEST_DB_PATH="$2"
            shift 2
            ;;
        -q|--quick)
            check_prerequisites
            quick_test
            exit $FAILED_TESTS
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Run main function
main 