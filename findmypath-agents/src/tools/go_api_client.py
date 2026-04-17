"""
Async HTTP client for calling Go backend SmartApply APIs.

Provides type-safe wrapper around:
- GET /api/v1/smartapply/countries
- GET /api/v1/smartapply/schools
- GET /api/v1/smartapply/schools/:id
- GET /api/v1/smartapply/programs/:id

Uses httpx.AsyncClient with connection pooling, fine-grained timeouts,
and async context manager for proper lifecycle management.
"""

import os
import asyncio
import json
import logging
from typing import Optional, List, Dict, Any, AsyncIterator
from dataclasses import dataclass
import httpx
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class Country:
    """Country model from Go backend."""
    id: int
    name: str
    code: Optional[str] = None
    synced_at: Optional[str] = None


@dataclass
class School:
    """School model from Go backend."""
    id: int
    name: str
    category: Optional[str] = None
    country_id: Optional[int] = None
    country_name: Optional[str] = None
    city: Optional[str] = None
    address: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    website: Optional[str] = None
    logo: Optional[str] = None
    banner: Optional[str] = None
    content: Optional[str] = None
    programs_count: int = 0
    synced_at: Optional[str] = None


@dataclass
class Program:
    """Program model from Go backend."""
    id: int
    name: str
    school_id: int
    intake: Optional[List[str]] = None
    document_requirements: Optional[Dict[str, Any]] = None
    synced_at: Optional[str] = None


class AsyncGoAPIClient:
    """
    Async HTTP client for PathCan Go backend SmartApply APIs.
    
    Features:
    - Connection pooling with limits
    - Fine-grained timeouts (connect, read, write, pool)
    - Async context manager for lifecycle management
    - Proper error handling and retries
    
    Usage:
        async with AsyncGoAPIClient() as client:
            countries = await client.get_countries()
            schools = await client.search_schools(country_id=1, gpa=3.5)
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        write_timeout: float = 10.0,
        pool_timeout: float = 30.0,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
        max_retries: int = 3
    ):
        """
        Initialize Async Go API client.
        
        Args:
            base_url: Go backend URL (default: from GO_BACKEND_URL env)
            connect_timeout: Connection timeout in seconds
            read_timeout: Read timeout in seconds  
            write_timeout: Write timeout in seconds
            pool_timeout: Pool acquisition timeout in seconds
            max_connections: Maximum total connections
            max_keepalive_connections: Maximum keep-alive connections
            max_retries: Maximum retry attempts for failed requests
        """
        self.base_url = (
            base_url or 
            os.getenv("GO_BACKEND_URL", "http://localhost:8080")
        ).rstrip("/")
        
        # Fine-grained timeouts
        self.timeouts = httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout
        )
        
        # Connection pooling limits
        self.limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections
        )
        
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(
            f"AsyncGoAPIClient initialized with base_url={self.base_url}, "
            f"timeouts={self.timeouts}, limits={self.limits}"
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeouts,
                limits=self.limits,
                follow_redirects=True
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _make_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make async HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/api/v1/smartapply/countries")
            params: Query parameters
            json_data: JSON payload for POST/PUT requests
        
        Returns:
            JSON response data or None if failed
        """
        if self._client is None:
            raise RuntimeError("Client not initialized. Use as async context manager.")
        
        url = f"{self.base_url}{path}"
        
        for attempt in range(self.max_retries):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data
                )
                
                logger.debug(
                    f"Go API {method} {path} - Status: {response.status_code}"
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Go API {path} returned 404")
                    return None
                elif response.status_code >= 500:
                    # Retry server errors
                    logger.warning(
                        f"Go API server error: {response.status_code} - {response.text[:200]}"
                    )
                    if attempt < self.max_retries - 1:
                        # Exponential backoff
                        await asyncio.sleep(0.5 * (2 ** attempt))
                        continue
                else:
                    logger.error(
                        f"Go API client error: {response.status_code} - {response.text[:200]}"
                    )
                    break
                    
            except httpx.TimeoutException:
                logger.warning(
                    f"Go API timeout (attempt {attempt + 1}/{self.max_retries}): {url}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
            except httpx.RequestError as e:
                logger.error(f"Go API request error: {e}")
                break
        
        return None
    
    async def get_countries(self) -> List[Country]:
        """
        Get list of all countries.
        
        API: GET /api/v1/smartapply/countries
        
        Returns:
            List of Country objects
        """
        logger.info("Fetching countries from Go backend")
        
        response = await self._make_request("GET", "/api/v1/smartapply/countries")
        
        if not response:
            return []
        
        # Parse response based on Go backend format
        # Assuming format: { "data": [...], "pagination": {...} }
        data = response.get("data", [])
        
        countries = []
        for item in data:
            country = Country(
                id=item.get("_id", item.get("id")),
                name=item.get("name", "Unknown"),
                code=item.get("code"),
                synced_at=item.get("synced_at")
            )
            countries.append(country)
        
        logger.info(f"Fetched {len(countries)} countries")
        return countries
    
    async def search_schools(
        self,
        country_id: Optional[int] = None,
        search: Optional[str] = None,
        gpa: Optional[float] = None,
        budget: Optional[float] = None,
        page: int = 1,
        limit: int = 20
    ) -> List[School]:
        """
        Search schools with filters.
        
        API: GET /api/v1/smartapply/schools
        
        Args:
            country_id: Filter by country ID
            search: Search term for school name
            gpa: Student GPA for matching
            budget: Budget constraint
            page: Page number
            limit: Items per page
        
        Returns:
            List of School objects
        """
        params = {
            "page": page,
            "limit": limit
        }
        
        if country_id:
            params["country_id"] = country_id
        if search:
            params["search"] = search
        if gpa is not None:
            params["gpa"] = str(gpa)
        if budget is not None:
            params["budget"] = str(budget)
        
        logger.info(f"Searching schools: country_id={country_id}, search={search}, gpa={gpa}, budget={budget}")
        
        response = await self._make_request("GET", "/api/v1/smartapply/schools", params)
        
        if not response:
            return []
        
        data = response.get("data", [])
        
        schools = []
        for item in data:
            school = School(
                id=item.get("_id", item.get("id")),
                name=item.get("name", "Unknown School"),
                category=item.get("category"),
                country_id=item.get("country_id"),
                country_name=item.get("country_name"),
                city=item.get("city"),
                address=item.get("address"),
                description=item.get("description"),
                website=item.get("website"),
                logo=item.get("logo"),
                banner=item.get("banner"),
                content=item.get("content"),
                programs_count=item.get("programs_count", 0),
                synced_at=item.get("synced_at")
            )
            schools.append(school)
        
        logger.info(f"Found {len(schools)} schools")
        return schools
    
    async def get_school_detail(self, school_id: int) -> Optional[School]:
        """
        Get detailed information for a specific school.
        
        API: GET /api/v1/smartapply/schools/:id
        
        Args:
            school_id: School ID
        
        Returns:
            School object or None if not found
        """
        logger.info(f"Fetching school detail: id={school_id}")
        
        response = await self._make_request(
            "GET", 
            f"/api/v1/smartapply/schools/{school_id}"
        )
        
        if not response:
            return None
        
        item = response.get("data", response)
        
        school = School(
            id=item.get("_id", item.get("id")),
            name=item.get("name", "Unknown School"),
            category=item.get("category"),
            country_id=item.get("country_id"),
            country_name=item.get("country_name"),
            city=item.get("city"),
            address=item.get("address"),
            description=item.get("description"),
            website=item.get("website"),
            logo=item.get("logo"),
            banner=item.get("banner"),
            content=item.get("content"),
            programs_count=item.get("programs_count", 0),
            synced_at=item.get("synced_at")
        )
        
        logger.info(f"Fetched school: {school.name}")
        return school
    
    async def get_programs(
        self,
        school_id: int,
        page: int = 1,
        limit: int = 20
    ) -> List[Program]:
        """
        Get programs for a specific school.
        
        API: GET /api/v1/smartapply/schools/:id/programs
        
        Args:
            school_id: School ID
            page: Page number
            limit: Items per page
        
        Returns:
            List of Program objects
        """
        params = {
            "page": page,
            "limit": limit
        }
        
        logger.info(f"Fetching programs for school: id={school_id}")
        
        response = await self._make_request(
            "GET",
            f"/api/v1/smartapply/schools/{school_id}/programs",
            params
        )
        
        if not response:
            return []
        
        data = response.get("data", [])
        
        programs = []
        for item in data:
            program = Program(
                id=item.get("_id", item.get("id")),
                name=item.get("name", "Unknown Program"),
                school_id=item.get("school_id", school_id),
                intake=item.get("intake", []),
                document_requirements=item.get("document_requirements"),
                synced_at=item.get("synced_at")
            )
            programs.append(program)
        
        logger.info(f"Found {len(programs)} programs for school {school_id}")
        return programs
    
    async def get_program_detail(self, program_id: int) -> Optional[Program]:
        """
        Get detailed information for a specific program.
        
        API: GET /api/v1/smartapply/programs/:id
        
        Args:
            program_id: Program ID
        
        Returns:
            Program object or None if not found
        """
        logger.info(f"Fetching program detail: id={program_id}")
        
        response = await self._make_request(
            "GET",
            f"/api/v1/smartapply/programs/{program_id}"
        )
        
        if not response:
            return None
        
        item = response.get("data", response)
        
        program = Program(
            id=item.get("_id", item.get("id")),
            name=item.get("name", "Unknown Program"),
            school_id=item.get("school_id"),
            intake=item.get("intake", []),
            document_requirements=item.get("document_requirements"),
            synced_at=item.get("synced_at")
        )
        
        logger.info(f"Fetched program: {program.name}")
        return program
    
    async def stream_agent_response(
        self,
        endpoint: str,
        json_data: Dict[str, Any]
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream agent response from Go backend.
        
        API: POST /api/v1/smartapply/agents/consult (streaming)
        
        Args:
            endpoint: API endpoint path
            json_data: Request payload
            
        Yields:
            SSE events as dictionaries
        """
        if self._client is None:
            raise RuntimeError("Client not initialized. Use as async context manager.")
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with self._client.stream(
                "POST",
                url,
                json=json_data,
                timeout=self.timeouts
            ) as response:
                if response.status_code != 200:
                    logger.error(f"Stream request failed: {response.status_code}")
                    return
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        if data_str.strip():
                            try:
                                event_data = json.loads(data_str)
                                yield event_data
                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON in SSE: {data_str[:100]}")
                                
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            raise


# Global client instance (lazy initialization)
_client: Optional[AsyncGoAPIClient] = None


async def get_async_client() -> AsyncGoAPIClient:
    """Get or create global AsyncGoAPIClient instance."""
    global _client
    if _client is None:
        _client = AsyncGoAPIClient()
    return _client


# Backward compatibility sync client (for non-async contexts)
class GoAPIClient:
    """
    Sync wrapper around AsyncGoAPIClient for backward compatibility.
    
    Note: This is less efficient than using the async client directly.
    Use AsyncGoAPIClient when possible.
    """
    
    def __init__(self, *args, **kwargs):
        self.async_client = AsyncGoAPIClient(*args, **kwargs)
    
    def get_countries(self) -> List[Country]:
        """Sync wrapper for get_countries."""
        async def fetch():
            async with self.async_client:
                return await self.async_client.get_countries()
        return asyncio.run(fetch())
    
    def search_schools(self, **kwargs) -> List[School]:
        """Sync wrapper for search_schools."""
        async def fetch():
            async with self.async_client:
                return await self.async_client.search_schools(**kwargs)
        return asyncio.run(fetch())
    
    def get_school_detail(self, school_id: int) -> Optional[School]:
        """Sync wrapper for get_school_detail."""
        async def fetch():
            async with self.async_client:
                return await self.async_client.get_school_detail(school_id)
        return asyncio.run(fetch())
    
    def get_programs(self, **kwargs) -> List[Program]:
        """Sync wrapper for get_programs."""
        async def fetch():
            async with self.async_client:
                return await self.async_client.get_programs(**kwargs)
        return asyncio.run(fetch())
    
    def get_program_detail(self, program_id: int) -> Optional[Program]:
        """Sync wrapper for get_program_detail."""
        async def fetch():
            async with self.async_client:
                return await self.async_client.get_program_detail(program_id)
        return asyncio.run(fetch())


def get_client() -> GoAPIClient:
    """Get sync client for backward compatibility."""
    return GoAPIClient()
