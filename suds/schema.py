# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# written by: Jeff Ortel ( jortel@redhat.com )

from suds import *
from suds.property import Property
from sax import Parser, splitPrefix
from urlparse import urljoin


class SchemaCollection(list):
    
    """ a collection of schemas providing a wrapper """
    
    def get_type(self, path):
        """ see Schema.get_type() """
        for s in self:
            result = s.get_type(path)
            if result is not None:
                return result
        return None


class Schema:
    
    """
    The schema is an objectification of a <schema/> (xsd) definition.
    It provides inspection, lookup and type resolution. 
    """
    
    def __init__(self, root, baseurl=None):
        """ construct the sequence object with a schema """
        self.root = root
        self.tns = self.__get_tns()
        self.baseurl = baseurl
        self.log = logger('schema')
        self.hints = {}
        self.types = {}
        self.children = []
        self.__add_children()
                
    def __add_children(self):
        """ populate the list of children """
        factory =\
            { 'import' : Import,
              'complexType' : Complex,
              'simpleType' : Simple,
              'element' : Element }
        for node in self.root.children:
            if node.name in factory:
                cls = factory[node.name]
                child = cls(self, node)
                self.children.append(child)
        self.children.sort()
                
    def __get_tns(self):
        """ get the target namespace """
        tns = [None, self.root.attribute('targetNamespace')]
        if tns[1] is not None:
            tns[0] = self.root.findPrefix(tns[1])
        return tuple(tns)
        
    def get_type(self, path):
        """
        get the definition object for the schema type located at the specified path.
        The path may contain (.) dot notation to specify nested types.
        The cached type is returned, else find_type() is used.
        """
        type = self.types.get(path, None)
        if type is None:
            type = self.__lookup(path)
            self.types[path] = type
        return type
    
    def __lookup(self, path):
        """
        get the definition object for the schema type located at the specified path.
        The path may contain (.) dot notation to specify nested types.
        """
        result = None
        parts = path.split('.')
        for child in self.children:
            name = child.get_name()
            if name is None:
                result = child.get_child(parts[0])
                if result is not None:
                    break
            else:
                if name == parts[0]:
                    result = child
                    break
        if result is not None:
            for name in parts[1:]:
                result = result.get_child(name)
                if result is None:
                    break
                result = result.resolve()
        return result
    
    def __str__(self):
        return str(self.root)


class SchemaProperty:
    
    """
    A schema property is an extension to property object with
    with schema awareness.
    """   

    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        self.root = root
        self.schema = schema
        self.log = schema.log
        self.children = []
        
    def namespace(self):
        """ get this properties namespace """
        return self.schema.tns
        
    def get_name(self):
        """ get the object's name """
        return None
    
    def get_type(self):
        """ get the node's (xsi) type as defined by the schema """
        return '_'
    
    def get_children(self, empty=None):
        """ get child (nested) schema definition nodes """ 
        list = self.children
        if len(list) == 0 and empty is not None:
            list = empty
        return list
    
    def get_child(self, name):
        """ get a child by name """
        for child in self.get_children():
            if child.get_name() == name:
                return child
        return None
    
    def unbounded(self):
        """ get whether this node's specifes that it is unbounded (collection) """
        return False
    
    def resolve(self):
        """ return the nodes true type when another named type is referenced. """
        result = self
        type = self.get_type()
        if self.custom():
            resolved = self.schema.get_type(type)
            if resolved is not None:
                result = resolved
        return result
    
    def custom(self):
        """ get whether this object schema type is custom """
        if self.get_type() is None:
            return False
        else:
            return (not self.builtin())
    
    def builtin(self):
        """ get whether this object schema type is an (xsd) builtin """
        try:
            prefix = self.get_type().split()[0]
            return prefix.startswith('xs')
        except:
            return False
        
    def __str__(self):
        return 'ns=%s, name=(%s), type=(%s)' \
            % (self.namespace(),
                  self.get_name(),
                  self.get_type())
    
    def __repr__(self):
        return self.__str__()


class Complex(SchemaProperty):
    
    """ Represents an (xsd) schema <xs:complexType/> node """
    
    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        SchemaProperty.__init__(self, schema, root)
        self.__add_children()
        self.children.sort()
        
    def get_name(self):
        """ gets the <xs:complexType name=""/> attribute value """
        return self.root.attribute('name')
        
    def __add_children(self):
        """ add <xs:sequence/> and <xs:complexContent/> nested types """
        for s in self.root.getChildren('sequence'):
            seq = Sequence(self.schema, s)
            for sc in seq.children:
                self.children.append(sc)
        for s in self.root.getChildren('complexContent'):
            cont = ComplexContent(self.schema, s)
            for cc in cont.children:
                self.children.append(cc)
                
    def __cmp__(self, other):
        if isinstance(other, (Simple, Element)):
            return -1
        else:
            return 0


class Simple(SchemaProperty):
    
    """ Represents an (xsd) schema <xs:simpleType/> node """
    
    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        SchemaProperty.__init__(self, schema, root)
        self.__add_children()
        self.children.sort()

    def get_name(self):
        """ gets the <xs:simpleType name=""/> attribute value """
        return self.root.attribute('name')

    def get_type(self):
        """ gets the <xs:simpleType xsi:type=""/> attribute value """
        return self.root.attribute('type')
        
    def __add_children(self):
        """ add <xs:enumeration/> nested types """
        for e in self.root.childrenAtPath('restriction/enumeration'):
            enum = Enumeration(self.schema, e)
            self.children.append(enum)
            
    def __cmp__(self, other):
        if isinstance(other, Element):
            return -1
        else:
            return 0


class Sequence(SchemaProperty):
    
    """ Represents an (xsd) schema <xs:sequence/> node """
    
    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        SchemaProperty.__init__(self, schema, root)
        self.__add_children()
        self.children.sort()

    def __add_children(self):
        """ add <xs:element/> nested types """
        for e in self.root.getChildren('element'):
            element = Element(self.schema, e)
            self.children.append(element)


class ComplexContent(SchemaProperty):
    
    """ Represents an (xsd) schema <xs:complexContent/> node """
    
    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        SchemaProperty.__init__(self, schema, root)
        self.__add_children()
        self.children.sort()

    def __add_children(self):
        """ add <xs:extension/> nested types """
        for e in self.root.getChildren('extension'):
            extension = Extension(self.schema, e)
            for ec in extension.children:
                self.children.append(ec)


class Enumeration(SchemaProperty):
    
    """ Represents an (xsd) schema <xs:enumeration/> node """

    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        SchemaProperty.__init__(self, schema, root)
        
    def get_name(self):
        """ gets the <xs:enumeration value=""/> attribute value """
        return self.root.attribute('attribute')

    
class Element(SchemaProperty):
    
    """ Represents an (xsd) schema <xs:element/> node """
    
    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        SchemaProperty.__init__(self, schema, root)
        self.__add_children()
        self.children.sort()
        
    def get_name(self):
        """ gets the <xs:element name=""/> attribute value """
        return self.root.attribute('name')
    
    def get_type(self):
        """ gets the <xs:element type=""/> attribute value """
        return self.root.attribute('type')
    
    def __add_children(self):
        """ add <complexType/>/* nested nodes """
        for c in self.root.getChildren('complexType'):
            complex = Complex(self.schema, c)
            for cc in complex.children:
                self.children.append(cc)
    
    def unbounded(self):
        """ get whether the element has a maxOccurs > 1 or unbounded """
        max = self.root.attribute('maxOccurs', default=1)
        return ( max > 1 or max == 'unbounded' )


class Extension(Complex):
    
    """ Represents an (xsd) schema <xs:extension/> node """
    
    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        Complex.__init__(self, schema, root)
        self.__add_children()
        self.children.sort()

    def __add_children(self):
        """ lookup extended type and add its children then add nested types """
        super = self.schema.get_type(self.root.attribute('base'))
        if super is None:
            return
        index = 0
        for sc in super.children:
            self.children.insert(index, sc)
            index += 1


class Import(SchemaProperty):
    
    """ Represents an (xsd) schema <xs:import/> node """
    
    def __init__(self, schema, root):
        """ create the object with a schema and root node """
        SchemaProperty.__init__(self, schema, root)   
        self.imported = None
        location = root.attribute('schemaLocation')
        if location is not None:
            self.__import(location)
        self.__add_children()
        self.children.sort()

    def namespace(self):
        """ get this properties namespace """
        return self.imported.tns

    def __add_children(self):
        """ add imported children """
        if self.imported is not None:
            for ic in self.imported.children:
                self.children.append(ic)

    def __import(self, uri):
        """ import the xsd content at the specified url """
        p = Parser()
        try:           
            if '://' not in uri:
                uri = urljoin(self.schema.baseurl, uri)
            imp_root = p.parse(url=uri).root()
            self.imported = Schema(imp_root, uri)
            self.__update_tns(imp_root)
            self.root.parent.replaceChild(self.root, imp_root)
            self.root = imp_root
            self.log.info('schema at (%s)\n\timported with tns=%s', uri, self.namespace())
        except tuple, e:
            self.log.error('imported schema at (%s), not-found\n\t%s', uri, str(e))
            
    def __update_tns(self, imp_root):
        """
        update the target namespace when the schema is imported
        specifying another namespace
        """
        impuri = self.root.attribute('namespace')
        if impuri is None:
            return
        prefixes = (imp_root.findPrefix(impuri), self.root.findPrefix(impuri))
        self.imported.tns = (prefixes[1], impuri)
        if prefixes[0] is None:
            return
        if prefixes[0] == prefixes[1]:
            return
        imp_root.clearPrefix(prefixes[0])
        imp_root.addPrefix(prefixes[1], impuri)
        self.__update_references(imp_root, prefixes)
        
    def __update_references(self, imp_root, prefixes):
        """ update all attributes with references to the old prefix to the new prefix """
        for a in imp_root.flattenedAttributes():
            value = a.getValue()
            if value is None: continue
            if ':' in value:
                p = value.split(':')
                if p[0] == prefixes[0]:
                    value = ':'.join((prefixes[1], value[1]))
                    a.setValue(value)
        
    def __cmp__(self, other):
        if isinstance(other, Complex):
            return -1
        else:
            return 0

        