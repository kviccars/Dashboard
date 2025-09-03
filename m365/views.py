from typing import Optional
import requests
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from .forms import M365ConfigForm
from .models import M365Config

logger = logging.getLogger(__name__)


def _get_singleton_config() -> Optional[M365Config]:
    return M365Config.objects.first()


def _acquire_app_token(config: M365Config):
    # Client credentials flow for Microsoft Graph
    import msal
    authority = f"https://login.microsoftonline.com/{config.tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=config.client_id,
        client_credential=config.client_secret,
        authority=authority,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result


def _acquire_sharepoint_token(config: M365Config):
    # Acquire resource-specific token for SharePoint (app-only)
    import msal
    authority = f"https://login.microsoftonline.com/{config.tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=config.client_id,
        client_credential=config.client_secret,
        authority=authority,
    )
    # For SharePoint REST the scope is the resource .default for the hostname
    sp_scope = f"https://{config.sharepoint_hostname}/.default"
    result = app.acquire_token_for_client(scopes=[sp_scope])
    return result


@login_required
def settings_view(request):
    config = _get_singleton_config()
    if request.method == 'POST':
        form = M365ConfigForm(request.POST, instance=config)
        if form.is_valid():
            config = form.save()
            messages.success(request, 'Saved Microsoft 365 configuration.')
            if request.POST.get('action') == 'test':
                result = _acquire_app_token(config)
                token = result.get('access_token') if isinstance(result, dict) else None
                if token:
                    messages.success(request, 'Connection successful. Token acquired.')
                else:
                    err = []
                    if isinstance(result, dict):
                        for key in ("error", "error_description", "suberror", "error_codes", "correlation_id", "trace_id"):
                            if key in result and result.get(key):
                                err.append(f"{key}: {result.get(key)}")
                    detail = "; ".join(err) or 'Unknown error'
                    messages.error(request, f'Failed to acquire token. {detail}')
            return redirect('settings')
    else:
        form = M365ConfigForm(instance=config)
    return render(request, 'settings.html', {'form': form})


@login_required
def list_sharepoint_lists(request):
    config = _get_singleton_config()
    if not config:
        messages.error(request, 'Please configure Microsoft 365 credentials first.')
        return redirect('settings')

    result = _acquire_app_token(config)
    token = result.get('access_token') if isinstance(result, dict) else None
    if not token:
        err = []
        if isinstance(result, dict):
            for key in ("error", "error_description", "suberror", "error_codes", "correlation_id", "trace_id"):
                if key in result and result.get(key):
                    err.append(f"{key}: {result.get(key)}")
        detail = "; ".join(err) or 'Unknown error'
        messages.error(request, f'Failed to acquire token. {detail}')
        return redirect('settings')

    headers = {"Authorization": f"Bearer {token}"}
    # Fetch the root SharePoint site, then its lists
    site_resp = requests.get('https://graph.microsoft.com/v1.0/sites/root', headers=headers, timeout=20)
    if site_resp.status_code != 200:
        messages.error(request, f"Failed to fetch site: {site_resp.status_code} {site_resp.text}")
        return redirect('settings')
    site_id = site_resp.json().get('id')

    lists_resp = requests.get(f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists', headers=headers, timeout=20)
    if lists_resp.status_code != 200:
        messages.error(request, f"Failed to fetch lists: {lists_resp.status_code} {lists_resp.text}")
        return redirect('settings')

    lists = lists_resp.json().get('value', [])
    return render(request, 'm365/lists.html', {'lists': lists})


@login_required
def list_views(request, list_id: str):
    config = _get_singleton_config()
    if not config:
        messages.error(request, 'Please configure Microsoft 365 credentials first.')
        return redirect('settings')

    result = _acquire_app_token(config)
    token = result.get('access_token') if isinstance(result, dict) else None
    if not token:
        err = []
        if isinstance(result, dict):
            for key in ("error", "error_description", "suberror", "error_codes", "correlation_id", "trace_id"):
                if key in result and result.get(key):
                    err.append(f"{key}: {result.get(key)}")
        detail = "; ".join(err) or 'Unknown error'
        messages.error(request, f'Failed to acquire token. {detail}')
        return redirect('settings')

    # If SharePoint hostname missing, fall back to Graph beta method
    if not config.sharepoint_hostname:
        headers = {"Authorization": f"Bearer {token}"}
        site_resp = requests.get('https://graph.microsoft.com/v1.0/sites/root', headers=headers, timeout=20)
        if site_resp.status_code != 200:
            messages.error(request, f"Failed to fetch site: {site_resp.status_code} {site_resp.text}")
            return redirect('settings')
        site_id = site_resp.json().get('id')

        views_url = f'https://graph.microsoft.com/beta/sites/{site_id}/lists/{list_id}/views'
        views_resp = requests.get(views_url, headers=headers, timeout=20)
        views: list = []
        if views_resp.status_code == 200:
            views = views_resp.json().get('value', [])
        else:
            expand_url = (
                f'https://graph.microsoft.com/beta/sites/{site_id}/lists/{list_id}'
                f'?$expand=views($select=id,displayName,isDefaultView,viewType)'
            )
            list_with_views_resp = requests.get(expand_url, headers=headers, timeout=20)
            if list_with_views_resp.status_code == 200:
                body = list_with_views_resp.json()
                if isinstance(body.get('views'), dict):
                    views = body.get('views', {}).get('value', [])
                else:
                    views = body.get('views') or []
            else:
                messages.error(
                    request,
                    (
                        "Failed to fetch views: "
                        f"{views_resp.status_code} {views_resp.text} | "
                        f"fallback {list_with_views_resp.status_code} {list_with_views_resp.text}"
                    ),
                )
                return redirect('m365_lists')
        return render(request, 'm365/views.html', {'views': views})

    # Use SharePoint REST with SharePoint resource token
    sp_result = _acquire_sharepoint_token(config)
    sp_token = sp_result.get('access_token') if isinstance(sp_result, dict) else None
    if not sp_token:
        err = []
        if isinstance(sp_result, dict):
            for key in ("error", "error_description", "suberror", "error_codes", "correlation_id", "trace_id"):
                if key in sp_result and sp_result.get(key):
                    err.append(f"{key}: {sp_result.get(key)}")
        detail = "; ".join(err) or 'Unknown error'
        messages.error(request, f'Failed to acquire SharePoint token. {detail}')
        return redirect('settings')

    sp_headers = {
        "Authorization": f"Bearer {sp_token}",
        "Accept": "application/json;odata=nometadata",
    }
    # For REST we need the list GUID; the list_id in Graph is often a composite id.
    # Attempt to resolve the list by Graph to get webUrl, then call SharePoint REST with ListId GUID.
    graph_headers = {"Authorization": f"Bearer {token}"}
    site_resp = requests.get('https://graph.microsoft.com/v1.0/sites/root', headers=graph_headers, timeout=20)
    if site_resp.status_code != 200:
        messages.error(request, f"Failed to fetch site: {site_resp.status_code} {site_resp.text}")
        return redirect('settings')
    site = site_resp.json()

    # Get list details including webUrl and possibly list/drive info
    list_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site.get('id')}/lists/{list_id}",
        headers=graph_headers,
        timeout=20,
    )
    if list_resp.status_code != 200:
        messages.error(request, f"Failed to fetch list details: {list_resp.status_code} {list_resp.text}")
        return redirect('m365_lists')
    list_body = list_resp.json()
    # The SharePoint REST expects the ListId GUID; in Graph beta, listBody may have 'id' as GUID already.
    list_guid = list_body.get('id')

    if not list_guid:
        messages.error(request, 'Could not resolve list GUID for SharePoint REST.')
        return redirect('m365_lists')

    sp_url = f"https://{config.sharepoint_hostname}/_api/web/lists(guid'{list_guid}')/views"
    sp_resp = requests.get(sp_url, headers=sp_headers, timeout=20)
    if sp_resp.status_code != 200:
        messages.error(request, f"Failed to fetch views (SharePoint REST): {sp_resp.status_code} {sp_resp.text}")
        return redirect('m365_lists')
    sp_views = sp_resp.json().get('value', []) if isinstance(sp_resp.json(), dict) else []
    # Normalize to fields used in template
    views = [
        {
            'displayName': v.get('Title'),
            'id': v.get('Id'),
            'isDefaultView': v.get('DefaultView'),
            'viewType': v.get('ViewType') or v.get('BaseViewId'),
        }
        for v in sp_views
    ]
    return render(request, 'm365/views.html', {'views': views})


@login_required
def timesheet_list(request):
    config = _get_singleton_config()
    if not config:
        messages.error(request, 'Please configure Microsoft 365 credentials first.')
        return redirect('settings')

    # Parameters
    page = max(int(request.GET.get('page', 1)), 1)
    page_size = min(max(int(request.GET.get('page_size', 10)), 1), 100)
    search = (request.GET.get('search') or '').strip()
    sort_by = request.GET.get('sort', 'Id')
    sort_desc = request.GET.get('desc', '').lower() == 'true'
    author_filter = (request.GET.get('author') or '').strip()
    customer_filter = (request.GET.get('customer') or '').strip()
    code_filters = request.GET.getlist('code')  # Multiple selection
    billable_filter = (request.GET.get('billable') or '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    # Acquire Graph token for resolving site and list id
    result = _acquire_app_token(config)
    token = result.get('access_token') if isinstance(result, dict) else None
    if not token:
        messages.error(request, 'Failed to acquire Graph token. Check credentials and API permissions.')
        return redirect('settings')
    graph_headers = {"Authorization": f"Bearer {token}"}

    # Resolve site id. If a specific site path is provided, use that; otherwise root
    if config.timesheet_site_path:
        # Use hostname + relative path to resolve site
        host = config.sharepoint_hostname or 'yourtenant.sharepoint.com'
        site_to_resolve = f"https://graph.microsoft.com/v1.0/sites/{host}:{config.timesheet_site_path}"
        logger.info(f"Resolving site: {site_to_resolve}")
        site_resp = requests.get(site_to_resolve, headers=graph_headers, timeout=20)
    else:
        logger.info("Using root site")
        site_resp = requests.get('https://graph.microsoft.com/v1.0/sites/root', headers=graph_headers, timeout=20)
    if site_resp.status_code != 200:
        logger.error(f"Site resolution failed: {site_resp.status_code} {site_resp.text}")
        messages.error(request, f"Failed to fetch site: {site_resp.status_code} {site_resp.text}")
        return redirect('settings')
    site_id = site_resp.json().get('id')
    logger.info(f"Site ID: {site_id}")

    # Find the list named 'timesheet'
    lists_resp = requests.get(f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists?$select=id,displayName', headers=graph_headers, timeout=20)
    if lists_resp.status_code != 200:
        logger.error(f"Lists fetch failed: {lists_resp.status_code} {lists_resp.text}")
        messages.error(request, f"Failed to fetch lists: {lists_resp.status_code} {lists_resp.text}")
        return redirect('settings')
    lists = lists_resp.json().get('value', [])
    logger.info(f"Found {len(lists)} lists: {[l.get('displayName') for l in lists]}")
    target_name = (config.timesheet_list_name or 'timesheet').lower()
    logger.info(f"Looking for list: '{target_name}'")
    ts = next((x for x in lists if (x.get('displayName') or '').lower() == target_name), None)
    if not ts:
        logger.error(f"List '{target_name}' not found")
        messages.error(request, f'Could not find a list named "{target_name}" on the selected site.')
        return redirect('m365_lists')
    list_id = ts.get('id')
    logger.info(f"Timesheet list ID: {list_id}")

    # Determine display columns from list schema so headers always render
    cols_resp = requests.get(
        f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/columns?$select=name,displayName,hidden,readOnly',
        headers=graph_headers,
        timeout=20,
    )
    schema_columns: list[str] = []
    if cols_resp.status_code == 200:
        col_defs = cols_resp.json().get('value', [])
        logger.info(f"Found {len(col_defs)} column definitions")
        # Prefer timesheet-specific columns, then add the rest that aren't hidden
        preferred_order = ['Author', 'Work_x0020_Date', 'Contractor', 'CustomerName', 'Customer_x0020_Name', 'Code', 'Hours', 'Mileage', 'Billable', 'Project', 'Status']
        available = {c.get('name'): c for c in col_defs if not c.get('hidden')}
        logger.info(f"Available columns: {list(available.keys())}")
        # Debug: Show column details
        for col in col_defs:
            logger.info(f"Column: {col.get('name')} (displayName: {col.get('displayName')}, hidden: {col.get('hidden')})")
        
        for key in preferred_order:
            if key in available and key not in schema_columns:
                schema_columns.append(key)
        for name in available.keys():
            if (name not in schema_columns and 
                not str(name).startswith('_') and 
                not str(name).lower().endswith('type') and
                str(name).lower() != 'type'):
                schema_columns.append(name)
    else:
        logger.error(f"Column fetch failed: {cols_resp.status_code} {cols_resp.text}")
    # Always include Id as the first column
    if 'Id' not in schema_columns:
        schema_columns = ['Id'] + schema_columns
    else:
        # Ensure Id is first
        schema_columns = ['Id'] + [c for c in schema_columns if c != 'Id']
    logger.info(f"Schema columns: {schema_columns}")

    # If SharePoint hostname provided, read items via SharePoint REST for better OData filtering/paging
    items = []
    all_items = []
    total = 0
    columns: list[str] = schema_columns[:8] if schema_columns else ['Id']
    logger.info(f"Display columns: {columns}")
    rows: list[dict] = []
    if config.sharepoint_hostname:
        logger.info("Using SharePoint REST API")
        sp_result = _acquire_sharepoint_token(config)
        sp_token = sp_result.get('access_token') if isinstance(sp_result, dict) else None
        if not sp_token:
            logger.error(f"SharePoint token acquisition failed: {sp_result}")
            messages.error(request, 'Failed to acquire SharePoint token. Set hostname and check permissions.')
            return redirect('settings')
        sp_headers = {
            "Authorization": f"Bearer {sp_token}",
            "Accept": "application/json;odata=nometadata",
        }
        # Use GUID id from Graph as list GUID
        filter_q = ''
        if search:
            # Simple contains filter against Title if present
            filter_q = f"&$filter=substringof('{search.replace("'", "''")}',Title)"
        skip = (page - 1) * page_size
        # For SharePoint REST, we need to use the site-relative URL, not the list GUID from Graph
        # Let's try a different approach - get the list by title first
        site_path = config.timesheet_site_path.rstrip('/') if config.timesheet_site_path else ''
        sp_url = (
            f"https://{config.sharepoint_hostname}{site_path}/_api/web/lists/getbytitle('{config.timesheet_list_name or 'timesheet'}')/items?"
            f"$top=1000&$orderby=Created desc{filter_q}"
        )
        logger.info(f"SharePoint REST URL: {sp_url}")
        logger.info(f"SharePoint token (first 20 chars): {sp_token[:20]}...")
        sp_resp = requests.get(sp_url, headers=sp_headers, timeout=20)
        if sp_resp.status_code != 200:
            logger.error(f"SharePoint REST failed: {sp_resp.status_code} {sp_resp.text}")
            logger.info("Falling back to Microsoft Graph API due to SharePoint REST failure")
            # Set flag to use Graph API fallback
            config.sharepoint_hostname = None
        else:
            body = sp_resp.json()
            items = body.get('value', [])
            logger.info(f"SharePoint REST returned {len(items)} items")
            # Map rows to the chosen columns (falling back if missing)
            rows = [
                {col: it.get(col) for col in columns if not str(col).startswith('@')}
                for it in items
            ]
            # SharePoint REST does not easily provide total count without another call; compute naive next/prev
            total = None
    
    # Use Graph API if SharePoint hostname not set or SharePoint REST failed
    if not config.sharepoint_hostname:
        # Fallback to Graph list items basic read
        logger.info("Using Microsoft Graph API")
        # Select only the fields we plan to display (excluding Id which is outside fields)
        select_fields = ','.join([c for c in columns if c != 'Id']) or 'Title'
        # Get latest 1000 entries, ordered by creation date descending to get most recent first
        graph_url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items?expand=fields($select={select_fields})&$top=1000&$orderby=fields/Created desc'
        logger.info(f"Graph URL: {graph_url}")
        items_resp = requests.get(graph_url, headers=graph_headers, timeout=20)
        if items_resp.status_code != 200:
            logger.error(f"Graph items fetch failed: {items_resp.status_code} {items_resp.text}")
            messages.error(request, f"Failed to fetch timesheet items: {items_resp.status_code} {items_resp.text}")
            return redirect('m365_lists')
        all_items = items_resp.json().get('value', [])
        logger.info(f"Graph returned {len(all_items)} items")
        # Determine dynamic columns from fields keys
        # Columns already decided from schema; ensure within max
        columns = columns[:8]
        # Build rows from items
        rows = []
        for it in all_items:
            fields = it.get('fields') or {}
            row = {'Id': it.get('id')}
            for col in columns:
                if col == 'Id':
                    continue
                row[col] = fields.get(col)
            rows.append(row)
        # Apply filters and search
        if search:
            q = search.lower()
            rows = [r for r in rows if q in ' '.join([str(v) for v in r.values() if v is not None]).lower()]
        if author_filter:
            # Author field might be a dict with LookupValue or a string
            def get_author_text(row):
                author_val = row.get('Author', '')
                if isinstance(author_val, dict):
                    return author_val.get('LookupValue', '')
                return str(author_val) if author_val else ''
            
            rows = [r for r in rows if author_filter.lower() in get_author_text(r).lower()]
        if customer_filter:
            rows = [r for r in rows if customer_filter.lower() in str(r.get('Customer_x0020_Name', '')).lower()]
        if code_filters:
            # Multiple code selection - include if any selected code matches
            rows = [r for r in rows if any(code.lower() in str(r.get('Code', '')).lower() for code in code_filters)]
        if billable_filter:
            rows = [r for r in rows if billable_filter.lower() in str(r.get('Billable', '')).lower()]
        
        # Date range filtering
        if date_from or date_to:
            from datetime import datetime
            def parse_date_value(date_val):
                if not date_val:
                    return None
                # Handle different date formats from SharePoint
                if isinstance(date_val, str):
                    try:
                        # Try ISO format first (2023-12-01T00:00:00Z)
                        if 'T' in date_val:
                            return datetime.fromisoformat(date_val.replace('Z', '+00:00')).date()
                        # Try simple date format (2023-12-01)
                        return datetime.strptime(date_val[:10], '%Y-%m-%d').date()
                    except:
                        return None
                return None
            
            def filter_by_date(row):
                # Use the specific Work_x0020_Date column
                work_date_field = 'Work_x0020_Date'
                row_date = None
                if work_date_field in row and row[work_date_field]:
                    row_date = parse_date_value(row[work_date_field])
                
                if not row_date:
                    return not (date_from or date_to)  # Include if no date filters
                
                if date_from:
                    try:
                        from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                        if row_date < from_date:
                            return False
                    except:
                        pass
                
                if date_to:
                    try:
                        to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
                        if row_date > to_date:
                            return False
                    except:
                        pass
                
                return True
            
            rows = [r for r in rows if filter_by_date(r)]
        
        # Sort rows
        if sort_by in columns and rows:
            rows.sort(key=lambda x: str(x.get(sort_by, '')).lower(), reverse=sort_desc)
        
        # Calculate sum of hours for filtered results (before pagination)
        total_hours = 0
        for row in rows:
            hours_val = row.get('Hours', 0)
            try:
                if isinstance(hours_val, (int, float)):
                    total_hours += hours_val
                elif isinstance(hours_val, str) and hours_val.strip():
                    total_hours += float(hours_val.strip())
            except (ValueError, TypeError):
                pass  # Skip invalid hour values
        
        total = len(rows)
        start = (page - 1) * page_size
        rows = rows[start:start + page_size]
        logger.info(f"Final rows after filtering/sorting/pagination: {len(rows)}, Total hours: {total_hours}")

    # Pagination flags for template (avoid arithmetic in template conditions)
    has_prev = page > 1
    if total is None:
        has_next = len(rows) == page_size
    else:
        has_next = (page * page_size) < total

    # Calculate total pages for pagination
    total_pages = (total + page_size - 1) // page_size if total else 1
    
    # Get unique values for filter dropdowns from all rows (before pagination)
    all_customers = set()
    all_codes = set()
    all_authors = set()
    all_billable = set()
    # Collect filter options from either SharePoint REST items or Graph API items
    if config.sharepoint_hostname and items:
        # For SharePoint REST, collect from items directly
        for it in items:
            all_customers.add(it.get('Customer_x0020_Name', ''))
            all_codes.add(it.get('Code', ''))
            all_billable.add(it.get('Billable', ''))
            author_field = it.get('Author')
            if isinstance(author_field, dict):
                all_authors.add(author_field.get('LookupValue', ''))
            else:
                all_authors.add(str(author_field) if author_field else '')
    elif all_items:
        # For Graph API, collect from all_items
        for it in all_items:
            fields = it.get('fields') or {}
            all_customers.add(fields.get('Customer_x0020_Name', ''))
            all_codes.add(fields.get('Code', ''))
            all_billable.add(fields.get('Billable', ''))
            author_field = fields.get('Author')
            if isinstance(author_field, dict):
                all_authors.add(author_field.get('LookupValue', ''))
            else:
                all_authors.add(str(author_field) if author_field else '')
    
    ctx = {
        'columns': columns,
        'rows': rows,
        'search': search,
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'sort_by': sort_by,
        'sort_desc': sort_desc,
        'author_filter': author_filter,
        'customer_filter': customer_filter,
        'code_filters': code_filters,
        'billable_filter': billable_filter,
        'date_from': date_from,
        'date_to': date_to,
        'total_hours': round(total_hours, 2),
        'authors': sorted([a for a in all_authors if a]),
        'customers': sorted([c for c in all_customers if c]),
        'codes': sorted([c for c in all_codes if c]),
        'billable_options': sorted([b for b in all_billable if b is not None and b != '']),
    }
    return render(request, 'm365/timesheet.html', ctx)


@login_required
def charts_view(request):
    """Charts view showing billable data visualization"""
    config = _get_singleton_config()
    if not config:
        messages.error(request, 'Please configure Microsoft 365 credentials first.')
        return redirect('settings')

    # Get author filter
    author_filter = (request.GET.get('author') or '').strip()

    # Get access token
    graph_result = _acquire_app_token(config)
    graph_token = graph_result.get('access_token') if isinstance(graph_result, dict) else None
    if not graph_token:
        logger.error(f"Graph token acquisition failed: {graph_result}")
        messages.error(request, f'Failed to acquire Graph token: {graph_result}')
        return redirect('settings')

    graph_headers = {
        "Authorization": f"Bearer {graph_token}",
        "Content-Type": "application/json",
    }

    # Resolve site ID
    site_path = config.timesheet_site_path.rstrip('/') if config.timesheet_site_path else ''
    if site_path:
        site_url = f'https://graph.microsoft.com/v1.0/sites/{config.sharepoint_hostname}:{site_path}'
    else:
        site_url = f'https://graph.microsoft.com/v1.0/sites/{config.sharepoint_hostname}'
    
    logger.info(f"Site URL: {site_url}")
    site_resp = requests.get(site_url, headers=graph_headers, timeout=10)
    if site_resp.status_code != 200:
        logger.error(f"Site resolution failed: {site_resp.status_code} {site_resp.text}")
        messages.error(request, f"Failed to resolve site: {site_resp.status_code} {site_resp.text}")
        return redirect('settings')
    
    site_id = site_resp.json().get('id')
    logger.info(f"Site ID: {site_id}")

    # Find the timesheet list
    lists_url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists'
    lists_resp = requests.get(lists_url, headers=graph_headers, timeout=10)
    if lists_resp.status_code != 200:
        logger.error(f"Lists fetch failed: {lists_resp.status_code} {lists_resp.text}")
        messages.error(request, f"Failed to fetch lists: {lists_resp.status_code} {lists_resp.text}")
        return redirect('settings')
    
    lists_data = lists_resp.json().get('value', [])
    timesheet_list_name = config.timesheet_list_name or 'timesheet'
    list_id = None
    for lst in lists_data:
        if lst.get('displayName', '').lower() == timesheet_list_name.lower():
            list_id = lst.get('id')
            break
    
    if not list_id:
        logger.error(f"Timesheet list '{timesheet_list_name}' not found")
        messages.error(request, f"Timesheet list '{timesheet_list_name}' not found")
        return redirect('settings')

    # Get all timesheet items
    items_url = f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items?expand=fields($select=Author,Billable,Hours,Work_x0020_Date)&$top=1000&$orderby=fields/Created desc'
    logger.info(f"Items URL: {items_url}")
    items_resp = requests.get(items_url, headers=graph_headers, timeout=20)
    if items_resp.status_code != 200:
        logger.error(f"Items fetch failed: {items_resp.status_code} {items_resp.text}")
        messages.error(request, f"Failed to fetch timesheet items: {items_resp.status_code} {items_resp.text}")
        return redirect('settings')
    
    all_items = items_resp.json().get('value', [])
    logger.info(f"Retrieved {len(all_items)} items for charts")

    # Process data for charts
    from datetime import datetime
    from collections import defaultdict
    
    billable_hours = {'True': 0.0, 'False': 0.0, 'Unknown': 0.0}
    monthly_data = defaultdict(lambda: {'True': 0.0, 'False': 0.0, 'Unknown': 0.0})
    all_authors = set()
    total_items = 0
    
    def parse_date_value(date_val):
        """Parse various date formats from SharePoint"""
        if not date_val:
            return None
        try:
            if isinstance(date_val, str):
                # Try common SharePoint date formats
                for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                    try:
                        return datetime.strptime(date_val, fmt)
                    except ValueError:
                        continue
        except:
            pass
        return None
    
    for item in all_items:
        fields = item.get('fields', {})
        
        # Get author info
        author_field = fields.get('Author')
        author_name = ''
        if isinstance(author_field, dict):
            author_name = author_field.get('LookupValue', '')
        else:
            author_name = str(author_field) if author_field else ''
        
        all_authors.add(author_name)
        
        # Apply author filter if specified
        if author_filter and author_filter.lower() not in author_name.lower():
            continue
        
        total_items += 1
        
        # Get hours value
        hours_val = fields.get('Hours', 0)
        hours = 0.0
        try:
            if isinstance(hours_val, (int, float)):
                hours = float(hours_val)
            elif isinstance(hours_val, str) and hours_val.strip():
                hours = float(hours_val.strip())
        except (ValueError, TypeError):
            hours = 0.0  # Default to 0 for invalid hour values
        
        # Get work date for monthly analysis
        work_date_val = fields.get('Work_x0020_Date')
        work_date = parse_date_value(work_date_val)
        
        # Sum hours by billable category
        billable_val = fields.get('Billable', '')
        billable_category = 'Unknown'
        if str(billable_val).lower() == 'true':
            billable_category = 'True'
        elif str(billable_val).lower() == 'false':
            billable_category = 'False'
        
        # Add to overall totals
        billable_hours[billable_category] += hours
        
        # Add to monthly data if we have a valid date
        if work_date:
            month_key = work_date.strftime('%Y-%m')
            monthly_data[month_key][billable_category] += hours

    # Prepare pie chart data
    pie_chart_data = {
        'labels': [],
        'data': [],
        'colors': []
    }
    
    color_map = {
        'True': '#107c10',   # Green for billable
        'False': '#d83b01',  # Red for non-billable  
        'Unknown': '#605e5c' # Gray for unknown
    }
    
    total_hours = sum(billable_hours.values())
    
    for label, hours in billable_hours.items():
        if hours > 0:  # Only include categories with data
            pie_chart_data['labels'].append(f'{label} ({hours:.1f}h)')
            pie_chart_data['data'].append(round(hours, 1))
            pie_chart_data['colors'].append(color_map[label])

    # Prepare monthly trend chart data
    sorted_months = sorted(monthly_data.keys())
    monthly_labels = []
    monthly_billable = []
    monthly_non_billable = []
    monthly_total = []
    
    for month_key in sorted_months:
        # Format month for display (e.g., "2024-01" -> "Jan 2024")
        try:
            month_date = datetime.strptime(month_key, '%Y-%m')
            monthly_labels.append(month_date.strftime('%b %Y'))
        except:
            monthly_labels.append(month_key)
        
        billable_hrs = round(monthly_data[month_key]['True'], 1)
        non_billable_hrs = round(monthly_data[month_key]['False'] + monthly_data[month_key]['Unknown'], 1)
        total_hrs = round(billable_hrs + non_billable_hrs, 1)
        
        monthly_billable.append(billable_hrs)
        monthly_non_billable.append(non_billable_hrs)
        monthly_total.append(total_hrs)

    monthly_chart_data = {
        'labels': monthly_labels,
        'billable': monthly_billable,
        'non_billable': monthly_non_billable,
        'total': monthly_total
    }

    ctx = {
        'pie_chart_data': pie_chart_data,
        'monthly_chart_data': monthly_chart_data,
        'author_filter': author_filter,
        'authors': sorted([a for a in all_authors if a]),
        'total_items': total_items,
        'total_hours': round(total_hours, 1),
        'billable_hours': {k: round(v, 1) for k, v in billable_hours.items()},
    }
    
    return render(request, 'm365/charts.html', ctx)


@login_required
def debug_columns(request):
    """Debug view to show all columns in the timesheet list"""
    config = _get_singleton_config()
    if not config:
        messages.error(request, 'Please configure Microsoft 365 credentials first.')
        return redirect('settings')

    # Acquire Graph token
    result = _acquire_app_token(config)
    token = result.get('access_token') if isinstance(result, dict) else None
    if not token:
        messages.error(request, 'Failed to acquire Graph token. Check credentials and API permissions.')
        return redirect('settings')
    graph_headers = {"Authorization": f"Bearer {token}"}

    # Resolve site id
    if config.timesheet_site_path:
        host = config.sharepoint_hostname or 'yourtenant.sharepoint.com'
        site_to_resolve = f"https://graph.microsoft.com/v1.0/sites/{host}:{config.timesheet_site_path}"
        site_resp = requests.get(site_to_resolve, headers=graph_headers, timeout=20)
    else:
        site_resp = requests.get('https://graph.microsoft.com/v1.0/sites/root', headers=graph_headers, timeout=20)
    
    if site_resp.status_code != 200:
        messages.error(request, f"Failed to fetch site: {site_resp.status_code} {site_resp.text}")
        return redirect('settings')
    site_id = site_resp.json().get('id')

    # Find the timesheet list
    lists_resp = requests.get(f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists?$select=id,displayName', headers=graph_headers, timeout=20)
    if lists_resp.status_code != 200:
        messages.error(request, f"Failed to fetch lists: {lists_resp.status_code} {lists_resp.text}")
        return redirect('settings')
    lists = lists_resp.json().get('value', [])
    target_name = (config.timesheet_list_name or 'timesheet').lower()
    ts = next((x for x in lists if (x.get('displayName') or '').lower() == target_name), None)
    if not ts:
        messages.error(request, f'Could not find a list named "{target_name}" on the selected site.')
        return redirect('m365_lists')
    list_id = ts.get('id')

    # Get all columns
    cols_resp = requests.get(
        f'https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/columns?$select=name,displayName,hidden,readOnly,columnGroup,description',
        headers=graph_headers,
        timeout=20,
    )
    
    columns = []
    if cols_resp.status_code == 200:
        col_defs = cols_resp.json().get('value', [])
        columns = [
            {
                'name': col.get('name'),
                'displayName': col.get('displayName'),
                'hidden': col.get('hidden'),
                'readOnly': col.get('readOnly'),
                'columnGroup': col.get('columnGroup'),
                'description': col.get('description'),
            }
            for col in col_defs
        ]
    else:
        messages.error(request, f"Failed to fetch columns: {cols_resp.status_code} {cols_resp.text}")
        return redirect('settings')

    return render(request, 'm365/debug_columns.html', {
        'columns': columns,
        'list_name': config.timesheet_list_name or 'timesheet',
        'site_path': config.timesheet_site_path or 'root site',
    })

