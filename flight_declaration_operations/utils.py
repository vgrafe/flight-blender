from scd_operations.scd_data_definitions import Altitude, Volume3D, Volume4D, LatLngPoint,OperationalIntentReference, Time
from scd_operations.scd_data_definitions import Polygon as Plgn
import shapely.geometry
from shapely.geometry import Point, Polygon
from shapely.geometry import shape
from pyproj import Proj

from typing import List
from geojson import FeatureCollection
import arrow
from shapely.ops import unary_union

class OperationalIntentsConverter():
    ''' A class to covert a operational Intnet  in to GeoJSON '''
    def __init__(self):
        self.geo_json = {"type":"FeatureCollection","features":[]}
        self.utm_zone = '54N'
        self.all_features = []
        
    def utm_converter(self, shapely_shape: shapely.geometry, inverse:bool=False) -> shapely.geometry.shape:
        ''' A helper function to convert from lat / lon to UTM coordinates for buffering. tracks. This is the UTM projection (https://en.wikipedia.org/wiki/Universal_Transverse_Mercator_coordinate_system), we use Zone 54N which encompasses Japan, this zone has to be set for each locale / city. Adapted from https://gis.stackexchange.com/questions/325926/buffering-geometry-with-points-in-wgs84-using-shapely '''

        proj = Proj(proj="utm", zone=self.utm_zone, ellps="WGS84", datum="WGS84")

        geo_interface = shapely_shape.__geo_interface__
        point_or_polygon = geo_interface['type']
        coordinates = geo_interface['coordinates']
        if point_or_polygon == 'Polygon':
            new_coordinates = [[proj(*point, inverse=inverse) for point in linring] for linring in coordinates]
        elif point_or_polygon == 'Point':
            new_coordinates = proj(*coordinates, inverse=inverse)
        else:
            raise RuntimeError('Unexpected geo_interface type: {}'.format(point_or_polygon))

        return shapely.geometry.shape({'type': point_or_polygon, 'coordinates': tuple(new_coordinates)})

    def convert_operational_intent_to_geo_json(self,extents: List[Volume4D]):
        for extent in extents:
            volume = extent['volume']            
            geo_json_features = self._convert_operational_intent_to_geojson_feature(volume)
            self.geo_json['features'] += geo_json_features


    def convert_geo_json_to_operational_intent(self, geo_json_fc: FeatureCollection, start_datetime: str, end_datetime:str) -> Volume4D:
        all_v4d = []
        all_shapes = []
        all_features = geo_json_fc['features']
        for feature in all_features:
            geom = feature['geometry']
            max_altitude = feature['properties']['max_altitude']['meters']
            min_altitude = feature['properties']['min_altitude']['meters']
            s = shape(geom)     
            all_shapes.append(s)

            feature_union = unary_union(all_shapes)
            b = feature_union.minimum_rotated_rectangle
            co_ordinates = list(zip(*b.exterior.coords.xy))

            # Convert bounds vertex list
            polygon_verticies = []
            for cur_co_ordinate in co_ordinates:
                v = LatLngPoint(lat =cur_co_ordinate[1],lng= cur_co_ordinate[0])
                polygon_verticies.append(v)

            # remove the final point
            polygon_verticies.pop()
                
            volume3D = Volume3D(outline_polygon=Plgn(vertices= polygon_verticies),altitude_lower=Altitude(value=max_altitude,reference='W84',units='M'), altitude_upper=Altitude(value=min_altitude,reference='W84',units='M'))

            volume4D = Volume4D(volume = volume3D, time_start=Time(format="RFC3339",value=start_datetime), time_end=Time(format="RFC3339", value=end_datetime))
            all_v4d.append(volume4D)
            
        o_i = OperationalIntentReference(extents= all_v4d,key= [], state ='Accepted',uss_base_url="https://flightblender.com")

        return o_i


        


    def get_geo_json_bounds(self) -> str:
            
        combined_features = unary_union(self.all_features)
        bnd_tuple = combined_features.bounds
        bounds = ''.join(['{:.7f}'.format(x) for x in bnd_tuple])

        return bounds    

    def _convert_operational_intent_to_geojson_feature(self, volume: Volume4D):
        
        geo_json_features = []
        
        if ('outline_polygon' in volume.keys()):
            outline_polygon = volume['outline_polygon']
            point_list = []
            for vertex in outline_polygon['vertices']:
                p = Point(vertex['lng'], vertex['lat'])
                point_list.append(p)
            outline_polygon = Polygon([[p.x, p.y] for p in point_list])
            self.all_features.append(outline_polygon)

            outline_p = shapely.geometry.mapping(outline_polygon)
            polygon_feature = {'type': 'Feature', 'properties': {}, 'geometry': outline_p}
            geo_json_features.append(polygon_feature)

        if ('outline_circle' in volume.keys() and volume['outline_circle'] is not None):
            outline_circle = volume['outline_circle']
            circle_radius = outline_circle['radius']['value']
            center_point = Point(outline_circle['center']['lng'],outline_circle['center']['lat'])
            utm_center = self.utm_converter(shapely_shape = center_point)
            buffered_cicle = utm_center.buffer(circle_radius)
            converted_circle = self.utm_converter(buffered_cicle, inverse=True)
            self.all_features.append(converted_circle)
            
            outline_c = shapely.geometry.mapping(converted_circle)

            circle_feature = {'type': 'Feature', 'properties': {}, 'geometry': outline_c}
            
            geo_json_features.append(circle_feature)
        
        return geo_json_features
