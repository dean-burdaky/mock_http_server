import argparse

import os.path as path

from typing import Union, Callable

from mock_http_server import Handler, load_handler


def print_indent( index : int ) -> None:
  for _i in range( index ):
    print( ' ', end='' )


def print_structure( struct : Union[ dict, list, tuple, str, int, float, bool, Callable, None ], \
                     eos : bool = False, indent : int = 0 ) -> None:
  if isinstance( struct, dict ):
    print( "{" )
    i = 0
    for key, value in struct.items():
      print_indent( indent + 2 )
      print( key, ":", end=' ' )
      is_last = i >= len( struct ) - 1
      print_structure( value, is_last, indent + 2 )
      if not is_last:
        print( "," )
      i += 1
    print_indent( indent )
    print( "}", end='\n' if eos else '' )
  elif isinstance( struct, list ):
    print( "[" )
    for i in range( len( struct ) ):
      is_last = i >= len( struct ) - 1
      print_indent( indent + 2 )
      print_structure( struct[i], is_last, indent + 2 )
      if not is_last:
        print( "," )
    print_indent( indent )
    print( "]", end='\n' if eos else '' )
  elif isinstance( struct, tuple ):
    print( "(" )
    for i in range( len( struct ) ):
      is_last = i >= len( struct ) - 1
      print_indent( indent + 2 )
      print_structure( struct[i], is_last, indent + 2 )
      if not is_last:
        print( "," )
    print_indent( indent )
    print( ")", end='\n' if eos else '' )
  else:
    print( repr( struct ), end='\n' if eos else '' )


def startup() -> None:
  parser = argparse.ArgumentParser( description="Executes passed handlerpy file and prints handler structure" )
  parser.add_argument( "handlerpy_file", type=str, help="File to open and execute" )
  parser.add_argument( "-s", "--suppress-print", action="store_true", help="Suppresses the printing of the handler structure", dest="suppress_print" )
  args = parser.parse_args()

  handler = None
  if path.exists( args.handlerpy_file ) and path.isfile( args.handlerpy_file ):
    handler = load_handler( args.handlerpy_file )

  if not args.suppress_print:
    print_structure( handler, True )
  else:
    print( "Handler loaded? " + handler != None )


if __name__ == "__main__":
  startup()