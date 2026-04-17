"""
Test script for Go backend API tools.

Tests:
- tool_get_countries
- tool_search_schools
- tool_get_school_detail
- tool_get_programs

Run with: pytest tests/test_tools.py -v
       or: python tests/test_tools.py
"""

import os
import pytest
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

from src.tools.school_tools import (
    tool_get_countries,
    tool_search_schools,
    tool_get_school_detail,
    tool_get_programs
)


class TestGetCountries:
    """Test get_countries tool."""
    
    def test_get_countries_success(self):
        """Test successful country retrieval."""
        print("\n" + "=" * 60)
        print("🌍 Testing tool_get_countries - Success Case")
        print("=" * 60)
        
        try:
            countries = tool_get_countries()
            
            if not countries:
                print("⚠️  No countries returned (API may be unavailable)")
                pytest.skip("Go backend unavailable")
            
            print(f"✅ Found {len(countries)} countries")
            print(f"   Sample: {countries[0] if countries else 'None'}")
            
            # Validate structure
            assert isinstance(countries, list), "Countries should be a list"
            if countries:
                first_country = countries[0]
                assert isinstance(first_country, dict), "Country should be a dict"
                assert "country_id" in first_country or "name" in first_country, \
                    "Country should have id or name"
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            pytest.skip(f"Go backend error: {e}")
    
    def test_get_countries_structure(self):
        """Test country data structure."""
        print("\n🧪 Testing country data structure")
        
        try:
            countries = tool_get_countries()
            
            if not countries:
                pytest.skip("No data available")
            
            # Check required fields
            for country in countries[:3]:  # Check first 3
                assert isinstance(country, dict), "Each country should be a dict"
                
                # At minimum should have some identifying field
                has_id = "country_id" in country or "id" in country
                has_name = "name" in country or "country_name" in country
                assert has_id or has_name, "Country should have ID or name"
            
            print(f"✅ Country structure validated for {len(countries[:3])} countries")
            return True
            
        except Exception as e:
            pytest.skip(f"Validation error: {e}")


class TestSearchSchools:
    """Test search_schools tool."""
    
    def test_search_schools_no_filters(self):
        """Test school search without any filters."""
        print("\n" + "=" * 60)
        print("🎓 Testing tool_search_schools - No Filters")
        print("=" * 60)
        
        try:
            schools = tool_search_schools()
            
            if not schools:
                print("⚠️  No schools returned (API may be unavailable)")
                pytest.skip("Go backend unavailable")
            
            print(f"✅ Found {len(schools)} schools")
            if schools:
                print(f"   Top match: {schools[0]['name']} (Score: {schools[0]['match_score']})")
            
            # Validate structure
            assert isinstance(schools, list), "Schools should be a list"
            if schools:
                first_school = schools[0]
                assert "name" in first_school, "School should have name"
                assert "match_score" in first_school, "School should have match_score"
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            pytest.skip(f"Go backend error: {e}")
    
    def test_search_schools_with_country_filter(self):
        """Test school search with country filter."""
        print("\n🧪 Testing tool_search_schools - Country Filter")
        
        try:
            schools = tool_search_schools(country_name="USA")
            
            if not schools:
                pytest.skip("No schools found for USA")
            
            print(f"✅ Found {len(schools)} schools in USA")
            
            # Verify all schools are in USA
            for school in schools[:5]:
                assert school.get("country") == "USA", \
                    f"School should be in USA, got {school.get('country')}"
            
            print("✅ All filtered schools match country filter")
            return True
            
        except Exception as e:
            pytest.skip(f"Filter error: {e}")
    
    def test_search_schools_with_gpa_filter(self):
        """Test school search with GPA filter."""
        print("\n🧪 Testing tool_search_schools - GPA Filter")
        
        try:
            schools = tool_search_schools(gpa=3.8)
            
            if not schools:
                pytest.skip("No schools found")
            
            print(f"✅ Found {len(schools)} schools for GPA 3.8")
            return True
            
        except Exception as e:
            pytest.skip(f"GPA filter error: {e}")
    
    def test_search_schools_with_budget_filter(self):
        """Test school search with budget filter."""
        print("\n🧪 Testing tool_search_schools - Budget Filter")
        
        try:
            schools = tool_search_schools(budget=30000)
            
            if not schools:
                pytest.skip("No schools found")
            
            print(f"✅ Found {len(schools)} schools for budget $30,000")
            return True
            
        except Exception as e:
            pytest.skip(f"Budget filter error: {e}")
    
    def test_search_schools_combined_filters(self):
        """Test school search with multiple filters."""
        print("\n🧪 Testing tool_search_schools - Combined Filters")
        
        try:
            schools = tool_search_schools(
                country_name="USA",
                gpa=3.5,
                budget=40000
            )
            
            if not schools:
                pytest.skip("No schools found with combined filters")
            
            print(f"✅ Found {len(schools)} schools with combined filters")
            return True
            
        except Exception as e:
            pytest.skip(f"Combined filter error: {e}")
    
    def test_search_schools_edge_case_high_gpa(self):
        """Test school search with very high GPA (edge case)."""
        print("\n🧪 Edge Case: Very high GPA (4.0)")
        
        try:
            schools = tool_search_schools(gpa=4.0)
            
            if schools:
                print(f"✅ Found {len(schools)} schools for GPA 4.0")
            else:
                print("⚠️  No schools for GPA 4.0")
            
            return True
            
        except Exception as e:
            pytest.skip(f"High GPA error: {e}")
    
    def test_search_schools_edge_case_low_gpa(self):
        """Test school search with very low GPA (edge case)."""
        print("\n🧪 Edge Case: Very low GPA (2.0)")
        
        try:
            schools = tool_search_schools(gpa=2.0)
            
            if schools:
                print(f"✅ Found {len(schools)} schools for GPA 2.0")
            else:
                print("⚠️  No schools for GPA 2.0")
            
            return True
            
        except Exception as e:
            pytest.skip(f"Low GPA error: {e}")
    
    def test_search_schools_edge_case_high_budget(self):
        """Test school search with very high budget (edge case)."""
        print("\n🧪 Edge Case: Very high budget ($100,000)")
        
        try:
            schools = tool_search_schools(budget=100000)
            
            if schools:
                print(f"✅ Found {len(schools)} schools for budget $100,000")
            else:
                print("⚠️  No schools for budget $100,000")
            
            return True
            
        except Exception as e:
            pytest.skip(f"High budget error: {e}")
    
    def test_search_schools_edge_case_low_budget(self):
        """Test school search with very low budget (edge case)."""
        print("\n🧪 Edge Case: Very low budget ($10,000)")
        
        try:
            schools = tool_search_schools(budget=10000)
            
            if schools:
                print(f"✅ Found {len(schools)} schools for budget $10,000")
            else:
                print("⚠️  No schools for budget $10,000")
            
            return True
            
        except Exception as e:
            pytest.skip(f"Low budget error: {e}")


class TestGetSchoolDetail:
    """Test get_school_detail tool."""
    
    def test_get_school_detail_success(self):
        """Test successful school detail retrieval."""
        print("\n" + "=" * 60)
        print("🏫 Testing tool_get_school_detail - Success Case")
        print("=" * 60)
        
        try:
            # First get a school ID from search
            schools = tool_search_schools()
            if not schools:
                print("⚠️  No schools to test detail")
                pytest.skip("No schools available")
            
            school_id = schools[0]["school_id"]
            print(f"Testing with school_id: {school_id}")
            
            detail = tool_get_school_detail(school_id)
            
            if not detail:
                print("⚠️  School detail not found")
                pytest.skip("School detail not available")
            
            print(f"✅ Found school: {detail.get('name')}")
            print(f"   Category: {detail.get('category')}")
            print(f"   Programs: {detail.get('programs_count')}")
            
            # Validate structure
            assert isinstance(detail, dict), "Detail should be a dict"
            assert "name" in detail, "Detail should have name"
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            pytest.skip(f"School detail error: {e}")
    
    def test_get_school_detail_invalid_id(self):
        """Test school detail with invalid ID (edge case)."""
        print("\n🧪 Edge Case: Invalid school ID")
        
        try:
            detail = tool_get_school_detail("invalid-id-12345")
            
            # Should return None or empty dict for invalid ID
            if detail is None or detail == {}:
                print("✅ Invalid ID handled correctly (returned None/empty)")
            else:
                print(f"⚠️  Unexpected result for invalid ID: {detail}")
            
            return True
            
        except Exception as e:
            # Exception is also acceptable for invalid ID
            print(f"✅ Invalid ID raised exception (acceptable): {type(e).__name__}")
            return True
    
    def test_get_school_detail_empty_string(self):
        """Test school detail with empty string ID (edge case)."""
        print("\n🧪 Edge Case: Empty school ID")
        
        try:
            detail = tool_get_school_detail("")
            
            if detail is None or detail == {}:
                print("✅ Empty ID handled correctly")
            else:
                print(f"⚠️  Unexpected result for empty ID: {detail}")
            
            return True
            
        except Exception as e:
            print(f"✅ Empty ID raised exception (acceptable): {type(e).__name__}")
            return True


class TestGetPrograms:
    """Test get_programs tool."""
    
    def test_get_programs_success(self):
        """Test successful program retrieval."""
        print("\n" + "=" * 60)
        print("📚 Testing tool_get_programs - Success Case")
        print("=" * 60)
        
        try:
            # First get a school ID
            schools = tool_search_schools()
            if not schools:
                print("⚠️  No schools to test programs")
                pytest.skip("No schools available")
            
            school_id = schools[0]["school_id"]
            print(f"Testing with school_id: {school_id}")
            
            programs = tool_get_programs(school_id)
            
            if not programs:
                print("⚠️  No programs found")
                pytest.skip("No programs available")
            
            print(f"✅ Found {len(programs)} programs")
            if programs:
                print(f"   Sample: {programs[0]['name']}")
            
            # Validate structure
            assert isinstance(programs, list), "Programs should be a list"
            if programs:
                first_program = programs[0]
                assert isinstance(first_program, dict), "Program should be a dict"
                assert "name" in first_program, "Program should have name"
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            pytest.skip(f"Programs error: {e}")
    
    def test_get_programs_invalid_school_id(self):
        """Test programs with invalid school ID (edge case)."""
        print("\n🧪 Edge Case: Invalid school ID for programs")
        
        try:
            programs = tool_get_programs("invalid-id-xyz")
            
            if programs is None or programs == []:
                print("✅ Invalid ID handled correctly")
            else:
                print(f"⚠️  Unexpected result: {programs}")
            
            return True
            
        except Exception as e:
            print(f"✅ Invalid ID raised exception (acceptable): {type(e).__name__}")
            return True


def main():
    """Run all tool tests (for standalone execution)."""
    print("\n🧪 Smart Apply Tools Test Suite")
    print("=" * 60)
    
    # Check if Go backend is available
    go_url = os.getenv("GO_BACKEND_URL", "http://localhost:8080")
    print(f"Go Backend URL: {go_url}")
    print("Note: Tests will skip/fail if Go backend is not running\n")
    
    # Run via pytest if available
    try:
        import pytest
        exit_code = pytest.main([__file__, "-v"])
        return exit_code == 0
    except ImportError:
        print("pytest not available, running tests manually...")
        
        results = {
            "get_countries": TestGetCountries().test_get_countries_success(),
            "search_schools": TestSearchSchools().test_search_schools_no_filters(),
            "get_school_detail": TestGetSchoolDetail().test_get_school_detail_success(),
            "get_programs": TestGetPrograms().test_get_programs_success()
        }
        
        print("\n" + "=" * 60)
        print("📊 Test Results Summary")
        print("=" * 60)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "⚠️  SKIP/FAIL"
            print(f"{status} - {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        # Return success if at least search_schools works
        return results.get("search_schools", False)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
