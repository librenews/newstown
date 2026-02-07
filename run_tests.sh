#!/bin/bash
# Test runner script with various options

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}News Town Test Suite${NC}\n"

# Default: fast tests only
if [ "$1" == "" ] || [ "$1" == "fast" ]; then
    echo -e "${GREEN}Running fast tests (excludes integration)...${NC}"
    pytest -v -m "not integration"

# All tests including integration
elif [ "$1" == "all" ]; then
    echo -e "${GREEN}Running all tests...${NC}"
    pytest -v -m ""

# Coverage report
elif [ "$1" == "coverage" ]; then
    echo -e "${GREEN}Running tests with coverage report...${NC}"
    pytest --cov=. --cov-report=html --cov-report=term-missing --cov-report=term:skip-covered
    echo -e "\n${GREEN}Coverage report generated at: htmlcov/index.html${NC}"

# Integration tests only
elif [ "$1" == "integration" ]; then
    echo -e "${GREEN}Running integration tests only...${NC}"
    pytest -v -m "integration"

# Specific file
elif [ "$1" == "file" ]; then
    if [ "$2" == "" ]; then
        echo "Usage: ./run_tests.sh file <filename>"
        exit 1
    fi
    echo -e "${GREEN}Running tests in $2...${NC}"
    pytest -v "$2"

# Watch mode (requires pytest-watch)
elif [ "$1" == "watch" ]; then
    echo -e "${GREEN}Running tests in watch mode...${NC}"
    echo "Install: pip install pytest-watch"
    ptw -- -v -m "not integration"

else
    echo "Unknown option: $1"
    echo ""
    echo "Usage:"
    echo "  ./run_tests.sh              # Fast tests (default)"
    echo "  ./run_tests.sh fast         # Fast tests only"
    echo "  ./run_tests.sh all          # All tests including integration"
    echo "  ./run_tests.sh integration  # Integration tests only"
    echo "  ./run_tests.sh coverage     # Tests with coverage report"
    echo "  ./run_tests.sh file <path>  # Specific test file"
    echo "  ./run_tests.sh watch        # Watch mode"
    exit 1
fi
