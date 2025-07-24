#!/bin/bash
set -e

# Integration Test Script for Two-Pod Runpod Architecture
echo "🧪 SQL Retriever Integration Test - Two Pod Architecture"

# Configuration
API_ENDPOINT="${API_ENDPOINT:-http://localhost:8080}"
EMBEDDING_URL="${EMBEDDING_URL:-http://localhost:8000}"
LLM_URL="${LLM_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-test-api-key}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() {
    echo -e "${BLUE}🔸 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_pattern="$3"
    
    print_step "Testing: $test_name"
    
    if output=$(eval "$test_command" 2>&1); then
        if [[ -z "$expected_pattern" ]] || echo "$output" | grep -q "$expected_pattern"; then
            print_success "$test_name passed"
            ((TESTS_PASSED++))
            return 0
        else
            print_error "$test_name failed - expected pattern '$expected_pattern' not found"
            echo "Output: $output"
            ((TESTS_FAILED++))
            return 1
        fi
    else
        print_error "$test_name failed - command execution error"
        echo "Output: $output"
        ((TESTS_FAILED++))
        return 1
    fi
}

echo "=================================================="
echo "🚀 Starting Integration Tests"
echo "=================================================="
echo "API Endpoint: $API_ENDPOINT"
echo "Embedding Service: $EMBEDDING_URL" 
echo "LLM Service: $LLM_URL"
echo "=================================================="

# Test 1: Health Check - Main API
print_step "Test 1: Main API Health Check"
run_test "Main API Health" \
    "curl -s -f $API_ENDPOINT/health" \
    "status"

# Test 2: Health Check - Embedding Service
print_step "Test 2: Embedding Service Health Check" 
run_test "Embedding Service Health" \
    "curl -s -f $EMBEDDING_URL/health" \
    "healthy"

# Test 3: Health Check - LLM Service  
print_step "Test 3: LLM Service Health Check"
run_test "LLM Service Health" \
    "curl -s -f $LLM_URL/v1/models" \
    "data"

# Test 4: Embedding Generation
print_step "Test 4: Embedding Generation"
run_test "Generate Embedding" \
    "curl -s -X POST $EMBEDDING_URL/embed -H 'Content-Type: application/json' -d '{\"text\": \"test query\"}'" \
    "embedding"

# Test 5: Search Similar Examples
print_step "Test 5: Search Similar Examples"
run_test "Search Examples" \
    "curl -s -X POST $EMBEDDING_URL/search -H 'Content-Type: application/json' -d '{\"question\": \"show me customers\", \"k\": 3}'" \
    "examples"

# Test 6: LLM SQL Generation
print_step "Test 6: LLM SQL Generation"
llm_prompt='<|begin_of_text|><|start_header_id|>system<|end_header_id|>Generate a SQL query.<|eot_id|><|start_header_id|>user<|end_header_id|>Show all customers<|eot_id|><|start_header_id|>assistant<|end_header_id|>SELECT'

run_test "LLM Generation" \
    "curl -s -X POST $LLM_URL/v1/completions -H 'Content-Type: application/json' -d '{\"model\": \"llama-3b-instruct\", \"prompt\": \"$llm_prompt\", \"max_tokens\": 50}'" \
    "choices"

# Test 7: Full End-to-End Query - Basic
print_step "Test 7: Full End-to-End Query - Basic"
run_test "End-to-End Basic Query" \
    "curl -s -X POST $API_ENDPOINT/query -H 'Authorization: Bearer $API_KEY' -H 'Content-Type: application/json' -d '{\"question\": \"show me all customers\"}'" \
    "sql_query"

# Test 8: Full End-to-End Query - Complex
print_step "Test 8: Full End-to-End Query - Complex"
run_test "End-to-End Complex Query" \
    "curl -s -X POST $API_ENDPOINT/query -H 'Authorization: Bearer $API_KEY' -H 'Content-Type: application/json' -d '{\"question\": \"what is the total revenue this year\"}'" \
    "sql_query"

# Test 9: Schema Endpoint
print_step "Test 9: Schema Information"
run_test "Schema Endpoint" \
    "curl -s -X GET $API_ENDPOINT/schema -H 'Authorization: Bearer $API_KEY'" \
    "schema"

# Test 10: Statistics Endpoint
print_step "Test 10: Statistics"
run_test "Statistics Endpoint" \
    "curl -s -X GET $API_ENDPOINT/stats -H 'Authorization: Bearer $API_KEY'" \
    "total_queries"

# Test 11: Error Handling - Invalid Query
print_step "Test 11: Error Handling"
run_test "Invalid Query Handling" \
    "curl -s -X POST $API_ENDPOINT/query -H 'Authorization: Bearer $API_KEY' -H 'Content-Type: application/json' -d '{\"question\": \"\"}'" \
    "error\\|sql_query"

# Test 12: Authentication Test
print_step "Test 12: Authentication"
run_test "Authentication Required" \
    "curl -s -o /dev/null -w '%{http_code}' -X POST $API_ENDPOINT/query -H 'Content-Type: application/json' -d '{\"question\": \"test\"}'" \
    "401"

# Performance Test
print_step "Performance Test: Multiple Concurrent Queries"
echo "Running 5 concurrent queries..."

pids=()
for i in {1..5}; do
    (
        start_time=$(date +%s%N)
        curl -s -X POST $API_ENDPOINT/query \
            -H "Authorization: Bearer $API_KEY" \
            -H "Content-Type: application/json" \
            -d '{"question": "count customers from USA"}' \
            > /tmp/test_result_$i.json
        end_time=$(date +%s%N)
        duration=$(( (end_time - start_time) / 1000000 ))
        echo "Query $i completed in ${duration}ms"
    ) &
    pids+=($!)
done

# Wait for all background jobs
for pid in "${pids[@]}"; do
    wait $pid
done

# Check results
concurrent_success=0
for i in {1..5}; do
    if grep -q "sql_query" /tmp/test_result_$i.json; then
        ((concurrent_success++))
    fi
done

print_step "Concurrent Test Results: $concurrent_success/5 successful"

if [ $concurrent_success -eq 5 ]; then
    print_success "Concurrent queries test passed"
    ((TESTS_PASSED++))
else
    print_error "Concurrent queries test failed"
    ((TESTS_FAILED++))
fi

# Cleanup
rm -f /tmp/test_result_*.json

echo "=================================================="
echo "🧪 Integration Test Results"
echo "=================================================="
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "Success Rate: $(( TESTS_PASSED * 100 / (TESTS_PASSED + TESTS_FAILED) ))%"
echo "=================================================="

if [ $TESTS_FAILED -eq 0 ]; then
    print_success "All tests passed! 🎉"
    echo
    print_step "✨ Your two-pod Runpod architecture is working correctly!"
    echo
    echo "🔗 Service Status:"
    echo "  - Main API: ✅ $API_ENDPOINT"
    echo "  - Embedding Service: ✅ $EMBEDDING_URL"  
    echo "  - LLM Service: ✅ $LLM_URL"
    echo
    echo "💰 Remember to monitor costs and stop pods when not needed"
    exit 0
else
    print_error "Some tests failed. Please check the services and try again."
    echo
    print_step "🔧 Troubleshooting Tips:"
    echo "  1. Ensure all services are running and accessible"
    echo "  2. Check API keys and authentication"
    echo "  3. Verify network connectivity between services"
    echo "  4. Check service logs for errors"
    exit 1
fi 