import unittest
import asyncio # Potentially needed if tests themselves are async directly without decorators

if __name__ == '__main__':
    print("Starting test suite discovery...")
    loader = unittest.TestLoader()
    # Discover tests in the 'tests' directory.
    # It will find subdirectories if they are packages (contain __init__.py)
    suite = loader.discover(start_dir='./tests', pattern='test_*.py')
    print(f"Found {suite.countTestCases()} test cases.")

    print("\nRunning tests...")
    runner = unittest.TextTestRunner(verbosity=2) # verbosity=2 for more detailed output
    result = runner.run(suite)

    if result.wasSuccessful():
        print("\nAll tests passed successfully!")
    else:
        print("\nSome tests failed.")
        # sys.exit(1) # Exit with error code if running in CI/CD
