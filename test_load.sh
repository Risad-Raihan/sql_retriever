#!/bin/bash
# Load Testing Script for SQL Retriever API
# Performs stress testing with various load patterns

set -e

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-test-api-key-12345}"
MAX_CONCURRENT="${MAX_CONCURRENT:-20}"
TEST_DURATION="${TEST_DURATION:-60}"
RAMP_UP_TIME="${RAMP_UP_TIME:-10}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Results tracking
TOTAL_REQUESTS=0
SUCCESSFUL_REQUESTS=0
FAILED_REQUESTS=0
TOTAL_RESPONSE_TIME=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Execute single request and track metrics
execute_request() {
    local endpoint="$1"
    local method="$2"
    local data="$3"
    local expected_status="$4"
    
    local start_time=$(date +%s.%3N)
    
    if [ "$method" = "POST" ]; then
        response=$(curl -s -w "%{http_code}" \
            -X POST "$API_BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $API_KEY" \
            -d "$data" \
            --connect-timeout 30 \
            --max-time 60 \
            2>/dev/null)
    else
        response=$(curl -s -w "%{http_code}" \
            -X GET "$API_BASE_URL$endpoint" \
            -H "Authorization: Bearer $API_KEY" \
            --connect-timeout 30 \
            --max-time 60 \
            2>/dev/null)
    fi
    
    local end_time=$(date +%s.%3N)
    local response_time=$(echo "$end_time - $start_time" | bc -l)
    
    http_code="${response: -3}"
    
    ((TOTAL_REQUESTS++))
    TOTAL_RESPONSE_TIME=$(echo "$TOTAL_RESPONSE_TIME + $response_time" | bc -l)
    
    if [[ "$http_code" == "$expected_status" ]]; then
        ((SUCCESSFUL_REQUESTS++))
        echo "✓ $endpoint - ${response_time}s - $http_code"
    else
        ((FAILED_REQUESTS++))
        echo "✗ $endpoint - ${response_time}s - $http_code (expected $expected_status)"
    fi
}

# Health check load test
test_health_load() {
    log_info "Testing health endpoint load..."
    
    for i in $(seq 1 $MAX_CONCURRENT); do
        execute_request "/health" "GET" "" "200" &
    done
    
    wait
    log_success "Health load test completed"
}

# Query endpoint load test
test_query_load() {
    log_info "Testing query endpoint load..."
    
    local queries=(
        '{"question": "How many customers are there?"}'
        '{"question": "Count products"}'
        '{"question": "Show customer distribution by country"}'
        '{"question": "What is total revenue?"}'
        '{"question": "List top 5 customers"}'
    )
    
    for i in $(seq 1 $MAX_CONCURRENT); do
        local query_idx=$((i % ${#queries[@]}))
        local query_data="${queries[$query_idx]}"
        execute_request "/query" "POST" "$query_data" "200" &
        
        # Stagger requests slightly
        sleep 0.1
    done
    
    wait
    log_success "Query load test completed"
}

# Mixed endpoint load test
test_mixed_load() {
    log_info "Testing mixed endpoint load..."
    
    for i in $(seq 1 $MAX_CONCURRENT); do
        case $((i % 4)) in
            0) execute_request "/health" "GET" "" "200" & ;;
            1) execute_request "/query" "POST" '{"question": "Count customers"}' "200" & ;;
            2) execute_request "/schema" "GET" "" "200" & ;;
            3) execute_request "/stats" "GET" "" "200" & ;;
        esac
        
        sleep 0.05
    done
    
    wait
    log_success "Mixed load test completed"
}

# Sustained load test
test_sustained_load() {
    log_info "Testing sustained load for ${TEST_DURATION}s..."
    
    local end_time=$(($(date +%s) + TEST_DURATION))
    local request_count=0
    
    while [[ $(date +%s) -lt $end_time ]]; do
        execute_request "/health" "GET" "" "200" &
        
        ((request_count++))
        
        # Control request rate (10 requests per second)
        if [[ $((request_count % 10)) -eq 0 ]]; then
            sleep 1
        fi
        
        # Prevent too many background processes
        if [[ $((request_count % 50)) -eq 0 ]]; then
            wait
        fi
    done
    
    wait
    log_success "Sustained load test completed"
}

# Ramp-up load test
test_ramp_up_load() {
    log_info "Testing ramp-up load over ${RAMP_UP_TIME}s..."
    
    local step_duration=$((RAMP_UP_TIME / 10))
    
    for step in $(seq 1 10); do
        local concurrent_requests=$((step * MAX_CONCURRENT / 10))
        
        log_info "Ramp-up step $step: $concurrent_requests concurrent requests"
        
        for i in $(seq 1 $concurrent_requests); do
            execute_request "/query" "POST" '{"question": "Test query"}' "200" &
        done
        
        sleep $step_duration
    done
    
    wait
    log_success "Ramp-up load test completed"
}

# Spike load test
test_spike_load() {
    log_info "Testing spike load..."
    
    # Normal load
    log_info "Phase 1: Normal load (5 requests)"
    for i in $(seq 1 5); do
        execute_request "/health" "GET" "" "200" &
    done
    wait
    
    sleep 2
    
    # Spike load
    log_info "Phase 2: Spike load ($MAX_CONCURRENT requests)"
    for i in $(seq 1 $MAX_CONCURRENT); do
        execute_request "/query" "POST" '{"question": "Spike test"}' "200" &
    done
    wait
    
    sleep 2
    
    # Return to normal
    log_info "Phase 3: Return to normal (5 requests)"
    for i in $(seq 1 5); do
        execute_request "/health" "GET" "" "200" &
    done
    wait
    
    log_success "Spike load test completed"
}

# Monitor system resources
monitor_resources() {
    local duration="$1"
    local output_file="load_test_resources.log"
    
    log_info "Monitoring system resources for ${duration}s..."
    
    {
        echo "timestamp,cpu_percent,memory_mb,connections"
        
        local end_time=$(($(date +%s) + duration))
        
        while [[ $(date +%s) -lt $end_time ]]; do
            local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
            
            # Get CPU and memory for uvicorn process
            local stats=$(ps -p $(pgrep -f "uvicorn" | head -1) -o %cpu,rss --no-headers 2>/dev/null || echo "0 0")
            local cpu_percent=$(echo $stats | awk '{print $1}')
            local memory_kb=$(echo $stats | awk '{print $2}')
            local memory_mb=$((memory_kb / 1024))
            
            # Count connections
            local connections=$(netstat -an 2>/dev/null | grep ":8000.*ESTABLISHED" | wc -l)
            
            echo "$timestamp,$cpu_percent,$memory_mb,$connections"
            
            sleep 1
        done
    } > "$output_file"
    
    log_success "Resource monitoring saved to $output_file"
}

# Performance analysis
analyze_performance() {
    if [[ $TOTAL_REQUESTS -gt 0 ]]; then
        local avg_response_time=$(echo "scale=3; $TOTAL_RESPONSE_TIME / $TOTAL_REQUESTS" | bc -l)
        local success_rate=$(echo "scale=2; $SUCCESSFUL_REQUESTS * 100 / $TOTAL_REQUESTS" | bc -l)
        
        echo "=================================="
        echo "📊 Load Test Results"
        echo "=================================="
        echo "Total Requests: $TOTAL_REQUESTS"
        echo "Successful: $SUCCESSFUL_REQUESTS"
        echo "Failed: $FAILED_REQUESTS"
        echo "Success Rate: ${success_rate}%"
        echo "Average Response Time: ${avg_response_time}s"
        echo "Total Test Time: ${TOTAL_RESPONSE_TIME}s"
        
        # Performance thresholds
        if (( $(echo "$avg_response_time < 5.0" | bc -l) )); then
            log_success "Average response time acceptable (< 5s)"
        else
            log_warning "Average response time high (> 5s)"
        fi
        
        if (( $(echo "$success_rate >= 95.0" | bc -l) )); then
            log_success "Success rate acceptable (≥ 95%)"
        else
            log_error "Success rate too low (< 95%)"
        fi
    fi
}

# Generate load test report
generate_report() {
    local report_file="load_test_report_$(date +%Y%m%d_%H%M%S).md"
    
    cat > "$report_file" << EOF
# Load Test Report - SQL Retriever API

**Generated:** $(date '+%Y-%m-%d %H:%M:%S')  
**Base URL:** $API_BASE_URL  
**Max Concurrent:** $MAX_CONCURRENT  
**Test Duration:** ${TEST_DURATION}s  

## Results Summary

| Metric | Value |
|--------|-------|
| Total Requests | $TOTAL_REQUESTS |
| Successful Requests | $SUCCESSFUL_REQUESTS |
| Failed Requests | $FAILED_REQUESTS |
| Success Rate | $(echo "scale=2; $SUCCESSFUL_REQUESTS * 100 / $TOTAL_REQUESTS" | bc -l)% |
| Average Response Time | $(echo "scale=3; $TOTAL_RESPONSE_TIME / $TOTAL_REQUESTS" | bc -l)s |

## Test Configuration

- **Concurrent Users:** $MAX_CONCURRENT
- **Test Duration:** ${TEST_DURATION}s
- **Ramp-up Time:** ${RAMP_UP_TIME}s
- **API Key:** ${API_KEY:0:10}...

## Performance Analysis

EOF

    local avg_response_time=$(echo "scale=3; $TOTAL_RESPONSE_TIME / $TOTAL_REQUESTS" | bc -l)
    local success_rate=$(echo "scale=2; $SUCCESSFUL_REQUESTS * 100 / $TOTAL_REQUESTS" | bc -l)
    
    if (( $(echo "$avg_response_time < 5.0" | bc -l) )); then
        echo "- ✅ Response time acceptable (< 5s)" >> "$report_file"
    else
        echo "- ❌ Response time too high (> 5s)" >> "$report_file"
    fi
    
    if (( $(echo "$success_rate >= 95.0" | bc -l) )); then
        echo "- ✅ Success rate acceptable (≥ 95%)" >> "$report_file"
    else
        echo "- ❌ Success rate too low (< 95%)" >> "$report_file"
    fi
    
    echo "" >> "$report_file"
    echo "## Recommendations" >> "$report_file"
    
    if [[ $FAILED_REQUESTS -gt 0 ]]; then
        echo "- Review failed requests and server logs" >> "$report_file"
        echo "- Consider implementing connection pooling" >> "$report_file"
    fi
    
    if (( $(echo "$avg_response_time > 10.0" | bc -l) )); then
        echo "- Optimize query processing pipeline" >> "$report_file"
        echo "- Consider caching frequently requested data" >> "$report_file"
    fi
    
    log_info "Load test report saved to: $report_file"
}

# Main execution
main() {
    echo "⚡ SQL Retriever Load Testing Suite"
    echo "=================================="
    echo "Base URL: $API_BASE_URL"
    echo "Max Concurrent: $MAX_CONCURRENT"
    echo "Test Duration: ${TEST_DURATION}s"
    echo "Ramp-up Time: ${RAMP_UP_TIME}s"
    echo "----------------------------------"
    
    # Check if server is available
    if ! curl -s "$API_BASE_URL/health" &> /dev/null; then
        log_error "Server not reachable at $API_BASE_URL"
        log_info "Please start the server first"
        exit 1
    fi
    
    # Start resource monitoring in background
    monitor_resources $((TEST_DURATION + RAMP_UP_TIME + 30)) &
    local monitor_pid=$!
    
    # Run load tests
    test_health_load
    sleep 2
    
    test_query_load
    sleep 2
    
    test_mixed_load
    sleep 2
    
    test_sustained_load
    sleep 2
    
    test_ramp_up_load
    sleep 2
    
    test_spike_load
    
    # Stop resource monitoring
    kill $monitor_pid 2>/dev/null || true
    
    # Analyze and report
    analyze_performance
    generate_report
    
    echo "=================================="
    if [[ $FAILED_REQUESTS -eq 0 ]]; then
        log_success "All load tests passed! 🎉"
        exit 0
    else
        log_error "Some load tests failed"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help"
    echo "  -u, --url URL          API base URL (default: http://localhost:8000)"
    echo "  -c, --concurrent N     Max concurrent requests (default: 20)"
    echo "  -d, --duration N       Test duration in seconds (default: 60)"
    echo "  -r, --rampup N         Ramp-up time in seconds (default: 10)"
    echo "  --quick                Quick load test (5 concurrent, 10s duration)"
    echo ""
    echo "Examples:"
    echo "  $0                     # Default load test"
    echo "  $0 --concurrent 50     # High concurrency test"
    echo "  $0 --quick             # Quick validation"
}

# Parse arguments
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
        -c|--concurrent)
            MAX_CONCURRENT="$2"
            shift 2
            ;;
        -d|--duration)
            TEST_DURATION="$2"
            shift 2
            ;;
        -r|--rampup)
            RAMP_UP_TIME="$2"
            shift 2
            ;;
        --quick)
            MAX_CONCURRENT=5
            TEST_DURATION=10
            RAMP_UP_TIME=3
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check dependencies
if ! command -v bc &> /dev/null; then
    log_error "bc command not found. Please install: sudo apt-get install bc"
    exit 1
fi

# Run main function
main 