import http
import http.server

import urllib

import os
import os.path as path

from ast           import literal_eval
from email.message import Message
from typing        import Any, Tuple, Dict, List, Union

Handler = Dict[ str, Any ]
HandlerNode = Dict[ str, Union[ Dict, List[ Handler ] ] ]

universal_encoding = "utf-8"

class DelegatingHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
  def do_HEAD( self ):
    self.send_response( http.HTTPStatus.OK )

  def do_GET( self ):
    handler = find_handler( "GET", self.path, self.headers, self.client_address )
    if handler == None:
      self.send_response( http.HTTPStatus.NOT_FOUND )
    self.send_response( http.HTTPStatus.OK )


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


def mime_type_map( mime_type_str : str ) -> Dict[ str, Tuple[ str, float ] ]:
  buckets = {}
  entries = mime_type_str.split( ',' )

  for entry in entries:
    mime_type_1, entry = entry.split( '/' )
    if '?' in entry:
      mime_type_2, quality = entry.split( '?' )
    else:
      mime_type_2 = entry
      quality = 1
    if not mime_type_1 in buckets:
      buckets[mime_type_1] = {}
    if not mime_type_2 in buckets[mime_type_1]:
      buckets[mime_type_1][mime_type_2] = quality

  return buckets


def accept_headers_match( handler : Handler, headers : Message ) -> bool:
  header = "Accept"
  t_mt_map = mime_type_map( handler["headers"][header] )
  r_mt_map = mime_type_map( headers[header] )
  accept_matched = False

  # Check */* for template
  if "*" in t_mt_map["*"] and len( r_mt_map ) > 0:
    accept_matched = True
  # Check */* for request
  elif "*" in r_mt_map["*"] and len( t_mt_map ) > 0:
    accept_matched = True
  # Check */<MT2> for template (special behaviour)
  else:
    for t_mt2 in t_mt_map["*"]:
      for r_mt1 in r_mt_map:
        if t_mt2 in r_mt_map[r_mt1]:
          accept_matched = True
          break
      if accept_matched:
        break

  # Found somethign with *?
  if accept_matched:
    return True
  # No valid maps for */<MT2>, remove it if we have it
  elif "*" in t_mt_map["*"]:
    t_mt_map.pop( "*" )
  
  # Check <MT1>
  for t_mt1 in t_mt_map:
    if t_mt1 in r_mt_map:
      # Check <MT1>/* for template/request
      if "*" in t_mt_map[t_mt1] or "*" in r_mt_map[t_mt1]
        accept_matched = True
        break
      # Check <MT1>/<MT2> for template
      else:
        for t_mt2 in t_mt_map[t_mt1]:
          if t_mt2 in r_mt_map[t_mt1]:
            accept_matched = True
            break
    if accept_matched:
      break

  return accept_matched


def find_handler_in_bucket( request_type : str, full_path : str, headers : Message, client : Tuple[ str, int ],
                            queries : Dict[ str, str ], bucket : List[ Handler ] ) -> Handler:
  for handler in bucket:
    matches = handler["request_type"] == request_type

    if "headers" in handler and matches:
      for header in handler["headers"]:
        if headers in headers:
          if header == "Accept":
            if not accept_headers_match( handler, header, headers )
              matches = False
          # Need to handle Content-Type

    if matches:
      if "queries" in handler and len( handler["queries"] ) == len( queries ):
          for param in handler["queries"]:
            if not param in queries or not isinstance( queries[param], handler["queries"][param] ):
              matches = False
              break
      elif "queries" in handler or len( queries ) > 0
        matches = False
    
    if matches:
      return handler
  
  return None


def find_handler_at_node( request_type : str, full_path : str, headers : Message, client : Tuple[ str, int ],
                          queries : Dict[ str, str ], path : str, parent : HandlerNode ) -> Handler:
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


def find_handler( request_type : str, path : str, headers : Message, client : Tuple[ str, int ] ) -> Handler:
  path_query_split = path.split( '?', 1 )[0]
  path_only = path_query_split[0]
  if len( path_query_split ) > 1:
    queries = deserialise_query_str( path_query_split[1] )
  
  return find_handler_at_node( request_type, path, headers, client, queries, path_only, handler_map )


def server_startup( handler_map : HandlerNode ) -> None:
  print( handler_map )


def startup( handlers_filename : str = None ) -> None:
  global handler_map

  if handlers_filename == None:
    handler_filenames = find_handler_files()
  else:
    handler_filenames = read_handlers_file( handlers_filename )

  handlers = load_handlers( handler_filenames )
  handler_map = map_handlers( handlers )
  server_startup( handler_map )


if __name__ == "__main__":
  startup()