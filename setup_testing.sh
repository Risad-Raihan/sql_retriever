#!/bin/bash
# Setup Script for SQL Retriever Testing Suite
# Makes all testing scripts executable and provides usage overview

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🔧 Setting up SQL Retriever Testing Suite${NC}"
echo "=================================================="

# Make scripts executable
chmod +x test_runner.py 2>/dev/null || echo "test_runner.py not found"
chmod +x test_manual.sh 2>/dev/null || echo "test_manual.sh not found"  
chmod +x test_load.sh 2>/dev/null || echo "test_load.sh not found"

if [ -f "test_runner.py" ]; then
    echo -e "${GREEN}✅ test_runner.py${NC} - Automated test suite with coverage"
fi

if [ -f "test_manual.sh" ]; then
    echo -e "${GREEN}✅ test_manual.sh${NC} - Manual endpoint testing with curl"
fi

if [ -f "test_load.sh" ]; then
    echo -e "${GREEN}✅ test_load.sh${NC} - Load testing and performance analysis"
fi

if [ -f "tests/test_api.py" ]; then
    echo -e "${GREEN}✅ tests/test_api.py${NC} - Comprehensive pytest test suite"
fi

if [ -f "TESTING_GUIDE.md" ]; then
    echo -e "${GREEN}✅ TESTING_GUIDE.md${NC} - Complete testing guide and troubleshooting"
fi

echo ""
echo -e "${YELLOW}📋 Testing Suite Usage:${NC}"
echo ""

echo -e "${BLUE}1. Automated Testing (Recommended):${NC}"
echo "   python test_runner.py                    # Full test suite with coverage"
echo "   python test_runner.py --quick            # Quick smoke tests"
echo "   python test_runner.py --coverage-threshold 85"
echo ""

echo -e "${BLUE}2. Manual Testing:${NC}"
echo "   bash test_manual.sh                      # Complete manual test suite"
echo "   bash test_manual.sh --quick              # Quick endpoint validation"
echo "   bash test_manual.sh --url http://localhost:8080"
echo ""

echo -e "${BLUE}3. Load Testing:${NC}"
echo "   bash test_load.sh                        # Default load testing"
echo "   bash test_load.sh --concurrent 50        # High concurrency test"
echo "   bash test_load.sh --quick                # Quick load validation"
echo ""

echo -e "${BLUE}4. Direct Pytest:${NC}"
echo "   pytest tests/test_api.py -v              # Run all tests"
echo "   pytest tests/test_api.py::TestQueryEndpoint -v"
echo "   pytest tests/test_api.py --cov=. --cov-report=html"
echo ""

echo -e "${YELLOW}🔍 Prerequisites:${NC}"
echo "1. Start the FastAPI server:"
echo "   uvicorn app:app --reload"
echo ""
echo "2. Set environment variables:"
echo "   export API_KEY='test-api-key-12345'"
echo "   export DATABASE_PATH='./data/test_crm_v1.db'"
echo ""
echo "3. Install test dependencies (automatic with test_runner.py):"
echo "   pip install pytest pytest-cov pytest-asyncio httpx"
echo ""

echo -e "${YELLOW}📁 Generated Reports:${NC}"
echo "   test_reports/           - Coverage and test reports"
echo "   *_test_report_*.md     - Manual and load test reports"
echo "   load_test_resources.log - Resource monitoring data"
echo ""

echo -e "${YELLOW}🆘 Troubleshooting:${NC}"
echo "   Read TESTING_GUIDE.md for detailed troubleshooting steps"
echo "   Common issues: DB connection, API key, model loading"
echo ""

echo "=================================================="
echo -e "${GREEN}✅ Testing suite setup complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Start your FastAPI server: uvicorn app:app --reload"
echo "2. Run quick test: python test_runner.py --quick"
echo "3. Run full suite: python test_runner.py" 