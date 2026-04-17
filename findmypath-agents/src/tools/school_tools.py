"""
School search tools for LangGraph agent.

Tools:
- get_countries: List all available countries
- search_schools: Search schools by criteria
- get_school_detail: Get detailed school information
- get_programs: Get programs for a school
- get_program_detail: Get program details
"""

import logging
from typing import List, Dict, Any, Optional
from src.tools.go_api_client import get_client, Country, School, Program

logger = logging.getLogger(__name__)


def tool_get_countries() -> List[Dict[str, Any]]:
    """
    Get list of all available countries.
    
    Returns:
        List of country dictionaries with id, name, code
    """
    logger.info("Tool: get_countries")
    
    client = get_client()
    countries = client.get_countries()
    
    if not countries:
        return [{"error": "No countries found or API unavailable"}]
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "code": c.code
        }
        for c in countries
    ]


def tool_search_schools(
    country_id: Optional[int] = None,
    country_name: Optional[str] = None,
    search: Optional[str] = None,
    gpa: Optional[float] = None,
    budget: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Search schools with filters.
    
    Args:
        country_id: Filter by country ID
        country_name: Filter by country name (will be converted to ID)
        search: Search term for school name
        gpa: User GPA for matching (used for ranking)
        budget: User budget for filtering (used for ranking)
    
    Returns:
        List of school dictionaries with details and match scores
    """
    logger.info(
        f"Tool: search_schools - country_id={country_id}, "
        f"search={search}, gpa={gpa}, budget={budget}"
    )
    
    client = get_client()
    
    # If country_name provided, need to resolve to ID
    # For now, pass country_id directly
    schools = client.search_schools(
        country_id=country_id,
        search=search,
        page=1,
        limit=20
    )
    
    if not schools:
        return []
    
    # Rank schools by match score (simplified ranking)
    ranked_schools = []
    for school in schools:
        match_score = 70.0  # Base score
        reasons = ["School found"]
        
        # Add ranking logic based on GPA and budget
        # This is simplified - real implementation would use program requirements
        if gpa and gpa >= 3.5:
            match_score += 10
            reasons.append("High GPA match")
        elif gpa and gpa >= 3.0:
            match_score += 5
            reasons.append("Good GPA match")
        
        if budget and budget >= 40000:
            match_score += 10
            reasons.append("Budget covers tuition")
        elif budget and budget >= 25000:
            match_score += 5
            reasons.append("Budget partially covers")
        
        ranked_schools.append({
            "school_id": str(school.id),
            "name": school.name,
            "country": school.country_name or "Unknown",
            "city": school.city or "Unknown",
            "match_score": min(match_score, 100),
            "reasons": reasons,
            "programs_count": school.programs_count,
            "category": school.category,
            "website": school.website,
            "logo": school.logo
        })
    
    # Sort by match score descending
    ranked_schools.sort(key=lambda x: x["match_score"], reverse=True)
    
    logger.info(f"Found {len(ranked_schools)} schools")
    return ranked_schools


def tool_get_school_detail(school_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information for a specific school.
    
    Args:
        school_id: School ID
    
    Returns:
        School details dictionary or None if not found
    """
    logger.info(f"Tool: get_school_detail - id={school_id}")
    
    try:
        school_id_int = int(school_id)
    except ValueError:
        logger.error(f"Invalid school_id: {school_id}")
        return None
    
    client = get_client()
    school = client.get_school_detail(school_id_int)
    
    if not school:
        return None
    
    return {
        "school_id": str(school.id),
        "name": school.name,
        "category": school.category,
        "country": school.country_name,
        "city": school.city,
        "address": school.address,
        "description": school.description,
        "website": school.website,
        "logo": school.logo,
        "banner": school.banner,
        "content": school.content,
        "programs_count": school.programs_count
    }


def tool_get_programs(
    school_id: str,
    search_query: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get programs for a specific school.
    
    Args:
        school_id: School ID
        search_query: Optional search term for program name
    
    Returns:
        List of program dictionaries
    """
    logger.info(f"Tool: get_programs - school_id={school_id}, search={search_query}")
    
    try:
        school_id_int = int(school_id)
    except ValueError:
        logger.error(f"Invalid school_id: {school_id}")
        return []
    
    client = get_client()
    programs = client.get_programs(school_id_int, page=1, limit=50)
    
    if not programs:
        return []
    
    # Filter by search query if provided
    if search_query:
        search_lower = search_query.lower()
        programs = [
            p for p in programs
            if search_lower in p.name.lower()
        ]
    
    return [
        {
            "program_id": str(p.id),
            "name": p.name,
            "school_id": str(p.school_id),
            "intake": p.intake or [],
            "has_requirements": bool(p.document_requirements)
        }
        for p in programs
    ]


def tool_get_program_detail(program_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information for a specific program.
    
    Args:
        program_id: Program ID
    
    Returns:
        Program details dictionary or None if not found
    """
    logger.info(f"Tool: get_program_detail - id={program_id}")
    
    try:
        program_id_int = int(program_id)
    except ValueError:
        logger.error(f"Invalid program_id: {program_id}")
        return None
    
    client = get_client()
    program = client.get_program_detail(program_id_int)
    
    if not program:
        return None
    
    return {
        "program_id": str(program.id),
        "name": program.name,
        "school_id": str(program.school_id),
        "intake": program.intake,
        "document_requirements": program.document_requirements
    }


# Tool configurations for LangGraph
TOOLS_CONFIG = {
    "get_countries": {
        "name": "get_countries",
        "description": "Get list of all available countries for studying abroad",
        "func": tool_get_countries,
        "parameters": {}
    },
    "search_schools": {
        "name": "search_schools",
        "description": "Search for schools by country, with optional GPA and budget filters",
        "func": tool_search_schools,
        "parameters": {
            "country_id": "Optional[int] - Filter by country ID",
            "country_name": "Optional[str] - Filter by country name",
            "search": "Optional[str] - Search term for school name",
            "gpa": "Optional[float] - User GPA for matching",
            "budget": "Optional[float] - User budget in USD"
        }
    },
    "get_school_detail": {
        "name": "get_school_detail",
        "description": "Get detailed information for a specific school",
        "func": tool_get_school_detail,
        "parameters": {
            "school_id": "str - School ID"
        }
    },
    "get_programs": {
        "name": "get_programs",
        "description": "Get list of programs for a specific school",
        "func": tool_get_programs,
        "parameters": {
            "school_id": "str - School ID",
            "search_query": "Optional[str] - Search term for program name"
        }
    },
    "get_program_detail": {
        "name": "get_program_detail",
        "description": "Get detailed information for a specific program",
        "func": tool_get_program_detail,
        "parameters": {
            "program_id": "str - Program ID"
        }
    }
}
