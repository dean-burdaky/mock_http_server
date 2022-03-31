import http
import http.server

import urllib

import os
import os.path as path
import argparse

from ast           import literal_eval
from email.message import Message
from typing        import Any, Tuple, Dict, List, Union

Handler = Dict[ str, Any ]
HandlerNode = Dict[ str, Union[ Dict, List[ Handler ] ] ]
Queries = Dict[ str, str ]
ResponseCode = int
ResponseHeaders = Dict[ str, str ]
EncResponseContent = bytes

universal_encoding = "utf-8"

class DelegatingHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
  def do_HEAD( self ):
    self.send_response( http.HTTPStatus.OK )

  def do_GET( self ):
    queries = find_queries( self.path )
    handler = find_handler( "GET", self.path, queries, self.headers, self.client_address )
    path_vars = None
    if handler != None:
      path_vars = find_path_vars( self.path )
      code, headers, content = hander["handle"]( self, self.client_address, queries, path_vars )
      self.send_response( code )
      for header_key in headers:
        self.send_header( header_key, headers[header_key] )
      self.end_headers()
      self.wfile.write( content )
    else:
      self.send_error( http.HTTPStatus.NOT_FOUND, "Unable to find handler for request", "Unable to find handler which matches with the request in one or more of: Path, queries, headers and path variables." )


def find_handler_files() -> List[ str ]:
  handler_filenames = [ 
    dir_entry.path
    for dir_entry in os.scandir()
    if dir_entry.name.endswith( ".handlerpy" ) and dir_entry.is_file()
  ]
  if len( handler_filenames ) == 0:
    print( "Error: Could not find any handler files in current directory" )

  return handler_filenames


def read_handers_file( handlers_filename : str ) -> List[ str ]:
  handler_filenames = []
  failed_line_reads = 0
  failed_file_read = True

  with open( handlers_filename, "rt", encoding=universal_encoding ) as handlers_file:
    for line in handlers_file:
      if path.exists( line ):
        handler_filenames.append( line )
      else:
        print( "Warning: Failed to find file '{}' referenced in {}".format( line, handlers_filename ) )
        failed_line_reads += 1
    failed_file_read = False

  if failed_file_read:
    handler_filenames = []
    print( "Error: Failed to fully read handlers file '{}'".format( handlers_filename ) )

  if failed_line_reads:
    print( "Warning: Failed to find files for {} lines in {}".format( failed_line_reads, handlers_filename ) )
  
  return handler_filenames


def load_handler( handler_filename : str ) -> Handler:
  handler_code = None
  handler = None

  with open( handler_filename, "rt", encoding=universal_encoding ) as handler_file:
    handler_code = handler_file.read()

  if handler_code != None:
    handler = {}
    try:
      exec( handler_code )
    except:
      handler = None

  return handler


def load_handlers( handler_filenames : List[ str ] ) -> List[ Handler ]:
  handlers = []
  failed_file_read = True

  for handler_filename in handler_filenames:
    handler = load_handler( handler_filename )
    if handler != None:
      handlers.append( handler )
      failed_file_read = False
    else:
      print( "Warning: Failed to load handler for file '{}'".format( handler_filename ) )

  if failed_file_read:
    print( "Error: Could not read any handler files" )

  return handlers


def map_handlers_at_node( handler : Handler, path : str, parent : HandlerNode ) -> bool:
  success = False

  split_path = path.split( '/', 1 )
  child_str = split_path[0]

  if child_str != "~~node~~":
    if not child_str in parent or parent[child_str] == None:
      parent[child_str] = {}

    if len( split_path ) > 1 and split_path[1] != '':
      subpath = split_path[1]
      success = map_handlers_at_node( handler, subpath, parent[child_str] )

    else:
      if not "~~node~~" in parent[child_str] or not isinstance( parent[child_str]["~~node~~"], list ):
        parent[child_str]["~~node~~"] = []
      parent[child_str]["~~node~~"].append( handler )
      success = handler in parent[child_str]["~~node~~"]
  else:
    print( "Warning: Node string '~~node~~' is reserved" )

  return success


def map_handlers( handlers : List[ Handler ] ) -> HandlerNode:
  handler_map = {}
  for handler in handlers:
    path = handler['path']
    if path[0] == '/':
      path = path.split( '?', 1 )[0]
      if not map_handlers_at_node( handler, path, handler_map ):
        print( "Warning: Failed to map handler with path '{}'".format( path ) )
    else:
      print( "Warning: Handler with path '{}' does not start with a '/'".format( path ) )
      
  return handler_map


def deserialise_query_str( query_str : str ) -> Dict[ str, Any ]:
  queries = {}

  kvp_strs = query_str.split( '&' )
  for kvp_str in kvp_strs:
    ksvp = kvp_str.split( '=' )
    if len( ksvp ) == 2:
      key = ksvp[0]
      try:
        value = literal_eval( ksvp[1] )
      except:
        value = ksvp[1]
      queries[key] = value
  
  return queries


def find_queries( path : str ) -> Queries:
  path_split  = path.split( '?', 1 )

  if len( path_split ) > 1:
    queries = deserialise_query_str( path_split[1] )
  else:
    queries = {}

  return queries


def mime_type_map( mime_type_str : str ) -> Dict[ str, Tuple[ str, float ] ]:
  buckets = {}
  entries = mime_type_str.split( ',' )

  for entry in entries:
    mime_type_1, entry = entry.split( '/', 1 )
    if ';' in entry:
      mime_type_2, entry = entry.split( ';', 1 )
      if '=' in entry:
        attribute_strs = entry.split( '=', 1 )
        attribute = ( attribute_strs[0], literal_eval( attribute_strs[1] ) )
      else:
        attribute = entry
    else:
      mime_type_2 = entry
      attribute = None
    if not mime_type_1 in buckets:
      buckets[mime_type_1] = {}
    if not mime_type_2 in buckets[mime_type_1]:
      buckets[mime_type_1][mime_type_2] = attribute

  return buckets


def accept_headers_match( t_accept_header : str, r_accept_header : str ) -> bool:
  t_mt_map = mime_type_map( t_accept_header )
  r_mt_map = mime_type_map( r_accept_header )

  # r_mt_map is empty, so the client hasn't properly defined what it can accept for a response
  if len( r_mt_map ) <= 0:
    return False

  # Template: */* - Handler supports responding in any content type
  if "*" in t_mt_map and "*" in t_mt_map["*"]:
    return True

  # Request: */* - Client can accept a response with any content type
  if "*" in r_mt_map and "*" in r_mt_map["*"]:
    return True

  # Template: mt1/? - Primary mime type that handler supports
  for t_mt1 in t_mt_map:
    # If client can accept the primary mime type
    if t_mt1 in r_mt_map:
      # Template: mt1/* - handler supports response in any secondary mime type
      if "*" in t_mt_map:
        return True

      # Template: mt1/mt2 - Content type composed of both primary and secondary mime types
      for t_mt2 in t_mt_map[t_mt1]:
        # If client can accept the content type
        if t_mt2 in r_mt_map[t_mt1]:
          return True

  return False


def content_type_headers_match( t_ct_header : str, r_ct_header : str ) -> bool:
  t_mt_map = mime_type_map( t_ct_header )
  if '/' in r_ct_header:
    r_mt1, temp = r_ct_header.split( '/', 1 )
    if ';' in temp:
      r_mt2, temp = temp.split( ';', 1 )
      if '=' in temp:
        attribute = temp.split( '=', 1 )
      else:
        attribute = temp
    else:
      attribute = None
  else:
    return False

  # */*
  if "*" in t_mt_map and "*" in t_mt_map["*"]:
    return True

  # Not mt1/?
  if not r_mt1 in t_mt_map:
    return False
  
  # mt1/*
  if "*" in t_mt_map[r_mt1]:
    return True

  # Not mt1/mt2
  if not r_mt2 in t_mt_map[r_mt1]:
    return False

  return True

def match_headers( hander : Handler, request_headers : Message ) -> bool:
  for header in handler["headers"]:
    if header in headers:
      if header.lower() == "accept":
        if not accept_headers_match( handler["headers"], headers )
          return False
      elif header.lower() == "content-type":
        if not content_type_headers_match( handler["headers"], headers )
          return False

  return True


def match_queries( hander : Handler, request_queries : Queries ) -> bool:
  if len( handler["queries"] ) == len( request_queries ):
    for param in handler["queries"]:
      if not param in request_queries or not isinstance( request_queries[param], handler["queries"][param] ):
        return False
  else:
    return False

  return True


def find_handler_in_bucket( request_type : str, full_path : str, headers : Message, client : Tuple[ str, int ],
                            queries : Queries, bucket : List[ Handler ] ) -> Handler:
  for handler in bucket:
    matches = handler["request_type"] == request_type

    if "headers" in handler and matches:
      matches = match_headers( handler, headers )

    if matches:
      if "queries" in handler:
        matches = match_queries( handler, queries )
      elif len( queries ) > 0
        matches = False
    
    if matches:
      return handler
  
  return None


def find_handler_at_node( request_type : str, full_path : str, headers : Message, client : Tuple[ str, int ],
                          queries : Queries, path : str, parent : HandlerNode ) -> Handler:
  handler = None

  split_path = path.split( '/', 1 )
  node_str  = split_path[0]
  subpath = split_path[1] if len( split_path ) > 1 else None

  path_var_keys = []
  for child_key in parent:
    problem = None

    if child_key == node_str:
      if subpath == None or subpath == '':
        bucket = parent[child_key]["~~node~~"]
        if bucket != None and isinstance( bucket, list ):
          handler = find_handler_in_bucket( request_type, full_path, headers, client, queries, bucket )

        else:
          problem = "'~~node~~' node at path {} is not a bucket/list".format( full_path )

      elif isinstance( parent[child_key], dict ):
        handler = find_handler_at_node( request_type, full_path, headers, client, queries, subpath, parent[child_key] )
      else:
        problem = "Handler map has invalid mapping for path {}".format( full_path )

      if handler != None and problem == None:
        break

    elif child_key.startswith( "$$" ) and child_key.endswith( "$$" ):
      path_var_keys.append( child_key )

    if problem != None:
      print( "Warning: {}".format( problem ) )
      break

  return handler


def find_handler( request_type : str, path : str, queries : Queries,
                  headers : Message, client : Tuple[ str, int ] ) -> Handler:
  global handler_map
              
  path_only = path.split( '?', 1 )[0]

  return find_handler_at_node( request_type, path, headers, client, queries, path_only, handler_map )

def find_path_vars( path : str, handler : Handler ) -> Dict[ str, Any ]:
  r_path = path.split( '?', 1 )[0]
  t_path = handler["path"]
  path_vars = []

  left_start = 0
  left_end = -1
  left_str = None
  right_start = 0
  right_end = -1
  right_str = None
  key_start = 0
  key_end = -1
  key_str = None
  value_start = -1
  value_end = 0
  value_str = None
  value = None

  left_end = t_path.find( "$$" )
  if left_end >= 0:
    left_str = t_path[left_start:left_end]
    value_start = r_path.find( left_str ) + len( left_str )
    value_end = -1
  while 0 <= left_end and left_end < len( t_path ):
    key_start = left_end + 2
    key_end = t_path.find( "$$", key_start )
    if key_end >= 0:
      key_str = t_path[key_start:key_end]
      right_start = key_end + 2
      right_end = t_path.find( "$$", right_start )
    if right_end >= 0:
      right_str = t_path[right_start:right_end]
      value_end = r_path.find( right_str, value_start )
      left_start = right_start
      left_end = right_end
      left_str = right_str
    if value_start >= 0 and value_end >= 0:
      value_str = r_path[value_start:value_end]
      try:
        value = literal_eval( value_str )
      except:
        return None
      value_start = value_end + len( right_str )
    if key_str != None and value != None:
      path_vars[key_str] = value
    key_str = None
    value = None

  return path_vars


def server_startup( handler_map : HandlerNode ) -> None:

  httpd = server.ThreadedHTTPServer()


def startup( handlers_filename : str = None ) -> None:
  global handler_map

  parser = argparse.ArgumentParser(description="Options for running the mock HTTP server")
  parser.add_argument( "-t", "--threaded", action="store_true", help="Option for using a threaded HTTP server" )
  parser.add_argument( "address", required=True, help="Address of the HTTP server to bind to" )
  parser.add_argument( "port", default=80, help="Port of the HTTP server to bind to" )
  parser.add_argument( "-s", "--ssl", nargs=2, metavars=("keyfile", "certfile"), type=str, help="Run server with SSL (port will not automatically default to 443, you will need to set it). A path to the key file and a path to the cert file will need to be set." )
  args = parser.parse_args()

  if handlers_filename == None:
    handler_filenames = find_handler_files()
  else:
    handler_filenames = read_handlers_file( handlers_filename )

  handlers = load_handlers( handler_filenames )
  handler_map = map_handlers( handlers )
  server_startup( handler_map )


if __name__ == "__main__":
  startup()