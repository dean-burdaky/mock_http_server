import http.server
import urllib.request

import os
import os.path as path

from typing import Any, Tuple, Dict, List, Union

Handler = Dict[ str, Any ]
HandlerNode = Dict[ str, Union[ Dict, List[ Handler ] ] ]

universal_encoding = "utf-8"

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

def server_startup( handler_map : HandlerNode ) -> None:
  print( handler_map )

def startup( handlers_filename : str = None ) -> None:
  if handlers_filename == None:
    handler_filenames = find_handler_files()
  else:
    handler_filenames = read_handlers_file( handlers_filename )

  handlers = load_handlers( handler_filenames )
  handler_map = map_handlers( handlers )
  server_startup( handler_map )

if __name__ == "__main__":
  startup()