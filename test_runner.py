#!/usr/bin/env python3
"""
Test Runner for SQL Retriever FastAPI Application
Executes comprehensive test suite with coverage reporting and result analysis.
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class TestRunner:
    """Comprehensive test runner with coverage analysis and reporting."""
    
    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path(__file__).parent
        self.test_dir = self.project_root / "tests"
        self.reports_dir = self.project_root / "test_reports"
        self.coverage_dir = self.reports_dir / "coverage"
        
        # Ensure directories exist
        self.reports_dir.mkdir(exist_ok=True)
        self.coverage_dir.mkdir(exist_ok=True)
        
        # Test configuration
        self.test_config = {
            'coverage_threshold': 80.0,
            'test_timeout': 300,  # 5 minutes
            'parallel_tests': True,
            'generate_html_report': True,
            'generate_xml_report': True,
            'generate_json_report': True,
        }
    
    def install_test_dependencies(self) -> bool:
        """Install required testing dependencies."""
        print("🔧 Installing test dependencies...")
        
        test_deps = [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-mock>=3.10.0",
            "pytest-xdist>=3.0.0",  # For parallel testing
            "httpx>=0.24.0",
            "coverage>=7.0.0",
            "pytest-html>=3.0.0",
            "pytest-json-report>=1.5.0"
        ]
        
        try:
            for dep in test_deps:
                result = subprocess.run([
                    sys.executable, "-m", "pip", "install", dep
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    print(f"❌ Failed to install {dep}: {result.stderr}")
                    return False
                    
            print("✅ Test dependencies installed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            print("❌ Dependency installation timed out")
            return False
        except Exception as e:
            print(f"❌ Error installing dependencies: {e}")
            return False
    
    def setup_test_environment(self) -> bool:
        """Setup test environment variables and configuration."""
        print("🔧 Setting up test environment...")
        
        # Set test environment variables
        test_env = {
            'TESTING': '1',
            'API_KEY': 'test-api-key-12345',
            'DATABASE_PATH': str(self.project_root / 'data' / 'test_crm_v1.db'),
            'RAG_ENABLED': 'true',
            'LOG_LEVEL': 'INFO',
            'ENVIRONMENT': 'test'
        }
        
        for key, value in test_env.items():
            os.environ[key] = value
        
        print("✅ Test environment configured")
        return True
    
    def run_unit_tests(self) -> Dict[str, Any]:
        """Run unit tests with coverage."""
        print("🧪 Running unit tests...")
        
        # Prepare pytest command
        pytest_cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir / "test_api.py"),
            "-v",
            "--tb=short",
            f"--cov={self.project_root}",
            f"--cov-report=html:{self.coverage_dir / 'html'}",
            f"--cov-report=xml:{self.coverage_dir / 'coverage.xml'}",
            f"--cov-report=json:{self.coverage_dir / 'coverage.json'}",
            f"--cov-report=term-missing",
            f"--cov-fail-under={self.test_config['coverage_threshold']}",
            f"--html={self.reports_dir / 'test_report.html'}",
            f"--json-report-file={self.reports_dir / 'test_report.json'}",
        ]
        
        # Add parallel execution if enabled
        if self.test_config['parallel_tests']:
            pytest_cmd.extend(["-n", "auto"])
        
        # Add timeout (if pytest-timeout is available)
        try:
            import pytest_timeout
            pytest_cmd.extend(["--timeout", str(self.test_config['test_timeout'])])
        except ImportError:
            pass  # Skip timeout if not available
        
        try:
            start_time = time.time()
            result = subprocess.run(
                pytest_cmd,
                capture_output=True,
                text=True,
                timeout=self.test_config['test_timeout']
            )
            end_time = time.time()
            
            # Parse results
            test_results = {
                'success': result.returncode == 0,
                'return_code': result.returncode,
                'duration': end_time - start_time,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'coverage_data': self._parse_coverage_results()
            }
            
            if test_results['success']:
                print("✅ Unit tests passed!")
            else:
                print("❌ Unit tests failed!")
                print(f"Error output: {result.stderr}")
            
            return test_results
            
        except subprocess.TimeoutExpired:
            print("❌ Unit tests timed out")
            return {
                'success': False,
                'return_code': -1,
                'duration': self.test_config['test_timeout'],
                'error': 'Test execution timed out'
            }
        except Exception as e:
            print(f"❌ Error running unit tests: {e}")
            return {
                'success': False,
                'return_code': -1,
                'error': str(e)
            }
    
    def run_integration_tests(self) -> Dict[str, Any]:
        """Run integration tests."""
        print("🔗 Running integration tests...")
        
        # Integration tests would test actual API endpoints with real database
        integration_cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir / "test_api.py::TestCloudSimulation"),
            str(self.test_dir / "test_api.py::TestAsyncIntegration"),
            "-v",
            "--tb=short",
            "-m", "not slow"  # Skip slow tests in regular runs
        ]
        
        try:
            start_time = time.time()
            result = subprocess.run(
                integration_cmd,
                capture_output=True,
                text=True,
                timeout=self.test_config['test_timeout']
            )
            end_time = time.time()
            
            return {
                'success': result.returncode == 0,
                'return_code': result.returncode,
                'duration': end_time - start_time,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
        except Exception as e:
            print(f"❌ Error running integration tests: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def run_load_tests(self) -> Dict[str, Any]:
        """Run load/performance tests."""
        print("⚡ Running load tests...")
        
        load_cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir / "test_api.py::TestAsyncIntegration::test_async_high_load_simulation"),
            "-v",
            "--tb=short"
        ]
        
        try:
            start_time = time.time()
            result = subprocess.run(
                load_cmd,
                capture_output=True,
                text=True,
                timeout=self.test_config['test_timeout']
            )
            end_time = time.time()
            
            return {
                'success': result.returncode == 0,
                'return_code': result.returncode,
                'duration': end_time - start_time,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
        except Exception as e:
            print(f"❌ Error running load tests: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _parse_coverage_results(self) -> Dict[str, Any]:
        """Parse coverage results from generated files."""
        coverage_data = {}
        
        try:
            # Parse JSON coverage report
            json_path = self.coverage_dir / "coverage.json"
            if json_path.exists():
                with open(json_path, 'r') as f:
                    coverage_json = json.load(f)
                    
                coverage_data = {
                    'total_coverage': coverage_json.get('totals', {}).get('percent_covered', 0),
                    'line_coverage': coverage_json.get('totals', {}).get('percent_covered_display', '0%'),
                    'files_covered': len(coverage_json.get('files', {})),
                    'missing_lines': coverage_json.get('totals', {}).get('missing_lines', 0),
                    'covered_lines': coverage_json.get('totals', {}).get('covered_lines', 0),
                    'total_lines': coverage_json.get('totals', {}).get('num_statements', 0)
                }
        except Exception as e:
            print(f"⚠️ Warning: Could not parse coverage results: {e}")
            
        return coverage_data
    
    def generate_summary_report(self, results: Dict[str, Any]) -> str:
        """Generate comprehensive test summary report."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"""
# SQL Retriever Test Report
Generated: {timestamp}

## Test Summary
- **Unit Tests**: {'✅ PASSED' if results.get('unit_tests', {}).get('success') else '❌ FAILED'}
- **Integration Tests**: {'✅ PASSED' if results.get('integration_tests', {}).get('success') else '❌ FAILED'}
- **Load Tests**: {'✅ PASSED' if results.get('load_tests', {}).get('success') else '❌ FAILED'}

## Coverage Report
"""
        
        coverage = results.get('unit_tests', {}).get('coverage_data', {})
        if coverage:
            report += f"""
- **Total Coverage**: {coverage.get('line_coverage', 'N/A')}
- **Files Covered**: {coverage.get('files_covered', 'N/A')}
- **Lines Covered**: {coverage.get('covered_lines', 'N/A')}/{coverage.get('total_lines', 'N/A')}
- **Missing Lines**: {coverage.get('missing_lines', 'N/A')}
"""
        else:
            report += "- Coverage data not available\n"
        
        report += f"""
## Performance Metrics
- **Unit Test Duration**: {results.get('unit_tests', {}).get('duration', 0):.2f}s
- **Integration Test Duration**: {results.get('integration_tests', {}).get('duration', 0):.2f}s
- **Load Test Duration**: {results.get('load_tests', {}).get('duration', 0):.2f}s
- **Total Test Duration**: {sum([
    results.get('unit_tests', {}).get('duration', 0),
    results.get('integration_tests', {}).get('duration', 0),
    results.get('load_tests', {}).get('duration', 0)
]):.2f}s

## Test Configuration
- **Coverage Threshold**: {self.test_config['coverage_threshold']}%
- **Test Timeout**: {self.test_config['test_timeout']}s
- **Parallel Execution**: {self.test_config['parallel_tests']}

## File Locations
- **HTML Coverage Report**: {self.coverage_dir / 'html' / 'index.html'}
- **XML Coverage Report**: {self.coverage_dir / 'coverage.xml'}
- **JSON Test Report**: {self.reports_dir / 'test_report.json'}
- **HTML Test Report**: {self.reports_dir / 'test_report.html'}

## Recommendations
"""
        
        # Add recommendations based on results
        total_coverage = coverage.get('total_coverage', 0)
        if total_coverage < self.test_config['coverage_threshold']:
            report += f"- 🔴 Coverage is below threshold ({total_coverage:.1f}% < {self.test_config['coverage_threshold']}%). Add more tests.\n"
        else:
            report += f"- ✅ Coverage meets threshold ({total_coverage:.1f}% >= {self.test_config['coverage_threshold']}%).\n"
        
        if not results.get('unit_tests', {}).get('success'):
            report += "- 🔴 Unit tests failing. Fix failing tests before deployment.\n"
        
        if not results.get('integration_tests', {}).get('success'):
            report += "- 🔴 Integration tests failing. Check API endpoint functionality.\n"
        
        if not results.get('load_tests', {}).get('success'):
            report += "- 🔴 Load tests failing. Review performance and concurrency handling.\n"
        
        return report
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run complete test suite."""
        print("🚀 Starting comprehensive test suite...")
        print("=" * 60)
        
        # Setup
        if not self.install_test_dependencies():
            return {'success': False, 'error': 'Failed to install dependencies'}
        
        if not self.setup_test_environment():
            return {'success': False, 'error': 'Failed to setup test environment'}
        
        # Run test suites
        results = {}
        
        # Unit tests
        results['unit_tests'] = self.run_unit_tests()
        
        # Integration tests
        results['integration_tests'] = self.run_integration_tests()
        
        # Load tests
        results['load_tests'] = self.run_load_tests()
        
        # Generate summary
        summary = self.generate_summary_report(results)
        summary_path = self.reports_dir / "test_summary.md"
        
        with open(summary_path, 'w') as f:
            f.write(summary)
        
        print("\n" + "=" * 60)
        print("📊 Test Summary:")
        print(summary)
        print(f"\n📁 Detailed reports saved to: {self.reports_dir}")
        
        # Overall success
        overall_success = (
            results.get('unit_tests', {}).get('success', False) and
            results.get('integration_tests', {}).get('success', False) and
            results.get('load_tests', {}).get('success', False)
        )
        
        results['overall_success'] = overall_success
        results['summary_path'] = str(summary_path)
        
        return results
    
    def quick_test(self) -> bool:
        """Run quick smoke tests for development."""
        print("⚡ Running quick smoke tests...")
        
        quick_cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir / "test_api.py::TestHealthEndpoint::test_health_check_success"),
            str(self.test_dir / "test_api.py::TestQueryEndpoint::test_query_success"),
            "-v"
        ]
        
        try:
            result = subprocess.run(quick_cmd, capture_output=True, text=True, timeout=60)
            success = result.returncode == 0
            
            if success:
                print("✅ Quick tests passed!")
            else:
                print("❌ Quick tests failed!")
                print(result.stderr)
                
            return success
            
        except Exception as e:
            print(f"❌ Error running quick tests: {e}")
            return False


def main():
    """Main test runner entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SQL Retriever Test Runner")
    parser.add_argument("--quick", "-q", action="store_true", 
                       help="Run quick smoke tests only")
    parser.add_argument("--coverage-threshold", type=float, default=80.0,
                       help="Coverage threshold percentage")
    parser.add_argument("--parallel", action="store_true", default=True,
                       help="Run tests in parallel")
    parser.add_argument("--timeout", type=int, default=300,
                       help="Test timeout in seconds")
    
    args = parser.parse_args()
    
    # Initialize test runner
    runner = TestRunner()
    runner.test_config.update({
        'coverage_threshold': args.coverage_threshold,
        'parallel_tests': args.parallel,
        'test_timeout': args.timeout
    })
    
    try:
        if args.quick:
            success = runner.quick_test()
            sys.exit(0 if success else 1)
        else:
            results = runner.run_all_tests()
            success = results.get('overall_success', False)
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        print("\n❌ Test execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test runner error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 