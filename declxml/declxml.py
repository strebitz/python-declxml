"""
declxml is a library for declaratively processing XML documents.

Processors
---------------
The declxml library uses processors to define the structure of XML documents. Processors can be
divided into two categories: *primitve processors* and *aggregate processors*.

Primitive Processors
----------------------
Primitive processors are used to parse and serialize simple, primitve values. The following module
functions are used to construct primitive processors:

.. autofunction:: declxml.boolean
.. autofunction:: declxml.floating_point
.. autofunction:: declxml.integer
.. autofunction:: declxml.string

Aggregate Processors
---------------------
Aggregate processors are composed of other processors. These processors are used for values such as
dictionaries, arrays, and user objects.

.. autofunction:: declxml.array
.. autofunction:: declxml.dictionary
.. autofunction:: declxml.user_object
"""
import warnings
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET


class XmlError(Exception):
    """Represents errors encountered when parsing XML data"""


class InvalidPrimitiveValue(XmlError):
    """Represents errors due to invalid primitive values"""


class InvalidRootProcessor(XmlError):
    """Represents errors due to an invalid root processor"""


class MissingValue(XmlError):
    """Represents errors due to a missing required element"""


def parse_from_file(root_proccesor, xml_file_path):
    """Parses the XML file using the processor as the root of the document"""
    with open(xml_file_path) as xml_file:
        xml_string = xml_file.read()
        parsed = parse_from_string(root_proccesor, xml_string)

    return parsed


def parse_from_string(root_processor, xml_string):
    """Parses the XML string using the processor as the root of the document."""
    if not _is_valid_root_processor(root_processor):
        raise InvalidRootProcessor('Invalid root processor')

    root = ET.fromstring(xml_string)
    _xml_namespace_strip(root)

    return root_processor.parse_at_root(root)


def serialize_to_string(root_processor, value, indent=None):
    """
    Serializes the value to an XML string using the root processor.

    :param indent: If specified, then the XML will be pretty formatted with the indentation.

    :return: The serialized XML string. If the omit_empty option was specified for the root
        processer, and the value is a Falsey value, then an empty string will be returned.
    """
    if not _is_valid_root_processor(root_processor):
        raise InvalidRootProcessor('Invalid root processor')

    root = root_processor.serialize(value)

    serialized = ET.tostring(root)

    # Why does element tree not support pretty printing XML?
    if indent:
        serialized = minidom.parseString(serialized).toprettyxml(indent=indent)

    return serialized


def array(item_processor, alias=None, nested=None):
    """
    Creates an array processor that can be used to parse and serialize array
    data.

    XML arrays may be nested within an array element, or they may be embedded
    within their parent. A nested array would look like:

    .. sourcecode:: xml

        <root-element>
            <some-element>ABC</some-element>
            <nested-array>
                <array-item>0</array-item>
                <array-item>1</array-item>
            </nested-array>
        </root-element>

    The corresponding embedded array would look like:

    .. sourcecode:: xml

        <root-element>
            <some-element>ABC</some-element>
            <array-item>0</array-item>
            <array-item>1</array-item>
        </root-element>


    :param item_processor: A declxml processor object for the items of the array.
    :param alias: If specified, the name given to the array when read from XML.
        If not specified, then the name of the items is used instead.
    :param nested: If the array is a nested array, then this should be the name of
        the element under which all array items are located. If not specified, then
        the array is treated as an embedded array.

    :return: A declxml processor object.
    """
    return _Array(item_processor, alias, nested)


def boolean(element_name, attribute=None, required=True, alias=None, default=False, omit_empty=False):
    """
    Creates a processor for boolean values.

    :param element_name: Name of the XML element containing the value
    :param attribute: If specified, then the value is searched for under the
        attribute within the element specified by element_name. If not specified,
        then the value is searched for as the contents of the element specified by
        element_name.
    :param required: Indicates whether the value is required when parsing and serializing.
    :param alias: If specified, then this is used as the name of the value when read from
        XML. If not specified, then the element_name is used as the name of the value.
    :param default: Default value to use if the element is not present. This option is only
        valid if required is specified as False.
    :param omit_empty: If True, then Falsey values will be ommitted when serializing to XML.

    :return: A declxml processor object.
    """
    return _PrimitiveValue(element_name, _parse_boolean, attribute, required, alias, default, omit_empty)


def dictionary(element_name, children, required=True, alias=None):
    """
    Creates a processor for dictionary values.

    :param element_name: Name of the XML element containing the dictionary value.
    :param children: List of declxml processor objects for processing the children
        contained within the dictionary.
    :param required: Indicates whether the value is required when parsing and serializing.
    :param alias: If specified, then this is used as the name of the value when read from
        XML. If not specified, then the element_name is used as the name of the value.

    :return: A declxml processor object.
    """
    return _Dictionary(element_name, children, required, alias)


def floating_point(element_name, attribute=None, required=True, alias=None, default=0.0, omit_empty=False):
    """
    Creates a processor for floating point values.

    See also :func:`declxml.boolean`
    """
    return _PrimitiveValue(element_name, _parse_float, attribute, required, alias, default, omit_empty)


def integer(element_name, attribute=None, required=True, alias=None, default=0, omit_empty=False):
    """
    Creates a processor for integer values.

    See also :func:`declxml.boolean`
    """
    return _PrimitiveValue(element_name, _parse_int, attribute, required, alias, default, omit_empty)


def string(element_name, attribute=None, required=True, alias=None, default='', strip_whitespace=True, omit_empty=False):
    """
    Creates a processor for integer values.

    :param strip_whitespace: Indicates whether leading and trailing whitespace should be stripped
        from parsed string values.

    See also :func:`declxml.boolean`
    """
    parser = _parse_string(strip_whitespace)
    return _PrimitiveValue(element_name, parser, attribute, required, alias, default, omit_empty)


def user_object(element_name, cls, child_processors, required=True, alias=None):
    """
    Creates a processor for user objects.

    :param cls: Class object with a no-argument constructor or other callable no-argument object.

    See also :func:`declxml.dictionary`
    """
    return _UserObject(element_name, cls, child_processors, required, alias)


class _Array(object):
    """An XML processor for Array values"""

    def __init__(self, item_processor, alias=None, nested=None):
        self._item_processor = item_processor
        self._nested = nested
        self.required = item_processor.required
        if alias:
            self.alias = alias
        elif nested:
            self.alias = nested
        else:
            self.alias = item_processor.alias

    def parse_at_element(self, element):
        """Parses the provided element as an array"""
        return self._parse(element)

    def parse_at_root(self, root):
        """Parses the root XML element as an array"""
        if not self._nested:
            raise InvalidRootProcessor('Non-nested array "{}" cannot be root element'.format(
                self.alias))

        parsed_array = []
        if root.tag == self._nested:
            parsed_array = self._parse(root)
        elif self.required:
            raise MissingValue('Missing required array: "{}"'.format(self.alias))

        return parsed_array

    def parse_from_parent(self, parent):
        """Parses the array data from the provided parent XML element"""
        if self._nested:
            item_iter = parent.find(self._nested)
        else:
            # The array's items are emebedded within the parent
            item_iter = parent.findall(self._item_processor.element_name)

        return self._parse(item_iter)

    def serialize(self, value):
        """
        Serializes the value into a new Element object and returns it.
        """
        if self._nested is None:
            raise InvalidRootProcessor('Cannot directly serialize a non-nested array: {}'.format(
                self.alias))

        if not value and self.required:
            raise MissingValue('Missing required array: "{}"'.format(
                self.alias))

        element = ET.Element(self._nested)
        self._serialize(element, value)

        return element

    def serialize_on_parent(self, parent, value):
        """Serializes value and appends it to the parent element"""
        if not value and self.required:
            raise MissingValue('Missing required array: "{}"'.format(
                self.alias))

        if self._nested is not None:
            array_parent = _element_get_or_add_from_parent(parent, self._nested)
        else:
            # Embedded array has all items serialized directly on the parent.
            array_parent = parent

        self._serialize(array_parent, value)

    def _parse(self, item_iter):
        """
        Parses the array data by using the provided iterator of XML elements to iterate over
        the item elements.
        """
        parsed_array = []

        if item_iter is not None:
            parsed_array = [self._item_processor.parse_at_element(item) for item in item_iter]

        if not parsed_array and self.required:
            raise MissingValue('Missing required array: "{}"'.format(self.alias))

        return parsed_array

    def _serialize(self, array_parent, value):
        """Serializes the array value adding it to the array parent element"""
        if not value:
            # Nothing to do. Avoid attempting to iterate over a possibly
            # None value.
            return

        for item_value in value:
            item_element = self._item_processor.serialize(item_value)
            array_parent.append(item_element)


class _Dictionary(object):
    """An XML processor for dictionary values"""

    def __init__(self, element_name, child_processors, required=True, alias=None):
        self.element_name = element_name
        self._child_processors = child_processors
        self.required = required
        if alias:
            self.alias = alias
        else:
            self.alias = element_name

    def parse_at_element(self, element):
        """Parses the provided element as a dictionary"""
        parsed_dict = {}

        if element is not None:
            for child in self._child_processors:
                parsed_dict[child.alias] = child.parse_from_parent(element)
        elif self.required:
            raise MissingValue('Missing required dictionary: "{}"'.format(self.element_name))

        return parsed_dict

    def parse_at_root(self, root):
        """Parses the root XML element as a dictionary"""
        parsed_dict = {}

        if root.tag == self.element_name:
            parsed_dict = self.parse_at_element(root)
        elif self.required:
            raise MissingValue('Missing required dictionary: "{}"'.format(self.element_name))

        return parsed_dict

    def parse_from_parent(self, parent):
        """Parses the dictionary data from the provided parent XML element"""
        element = parent.find(self.element_name)
        return self.parse_at_element(element)

    def serialize(self, value):
        """
        Serializes the value to a new element and returns the element.
        """
        if not value and self.required:
            raise MissingValue('Missing required dictionary: "{}"'.format(self.element_name))

        element = ET.Element(self.element_name)
        self._serialize(element, value)
        return element

    def serialize_on_parent(self, parent, value):
        """Serializes the value and adds it to the parent"""
        if not value and self.required:
            raise MissingValue('Missing required dictionary: "{}"'.format(
                self.element_name))

        if not value:
            return  # Do Nothing

        element = _element_get_or_add_from_parent(parent, self.element_name)
        self._serialize(element, value)

    def _serialize(self, element, value):
        """Serializes the dictionary appending all serialized children to the element"""
        for child in self._child_processors:
            child_value = value.get(child.alias)
            child.serialize_on_parent(element, child_value)


class _PrimitiveValue(object):
    """An XML processor for processing primitive values"""

    def __init__(self, element_name, parser_func, attribute=None, required=True, alias=None, default=None, omit_empty=False):
        """
        :param element_name: Name of the XML element containing the value.
        :param parser_func: Function to parse the raw XML value. Should take a string and return
            the value parsed from the raw string.
        :param required: Indicates whether the value is required.
        :param alias: Alternative name to give to the value. If not specified, element_name is used.
        :param default: Default value. Only valid if required is False.
        :param omit_empty: Omit the value when serializing if it is a falsey value. Only valid if required is
            False.
        """
        self.element_name = element_name
        self._parser_func = parser_func
        self._attribute = attribute
        self.required = required
        self._default = default

        if alias:
            self.alias = alias
        elif attribute:
            self.alias = attribute
        else:
            self.alias = element_name

        # If a value is required, then it will never be ommitted when serialized. This
        # is to ensure that data that is serialized by a processor can also be parsed
        # by a processor. Omitting required values would lead to an error when attempting
        # to parse the XML data. For primitives, a value must be None to be considered
        # missing, but is considered empty if it is falsey.
        if required:
            self.omit_empty = False
            if omit_empty:
                warnings.warn('omit_empty ignored on primitive values when required is specified')
        else:
            self.omit_empty = omit_empty


    def parse_at_element(self, element):
        """Parses the primitive value at the given XML element"""
        parsed_value = self._default

        if element is not None:
            if self._attribute:
                parsed_value = self._parse_attribute(element)
            else:
                parsed_value = self._parser_func(element.text)
        elif self.required:
            raise MissingValue('Missing required element: "{}"'.format(self.element_name))

        return parsed_value

    def parse_from_parent(self, parent):
        """Parses the primitive value under the provided parent XML element"""
        element = parent.find(self.element_name)
        return self.parse_at_element(element)

    def serialize(self, value):
        """
        Serializes the value into a new element object and returns the element. If the omit_empty
        option was specified and the value is falsey, then this will return None.
        """
        # For primitive values, this is only called when the value is part of an array,
        # in which case we do not need to check for missing or omitted values.      
        element = ET.Element(self.element_name)
        self._serialize(element, value)
        return element

    def serialize_on_parent(self, parent, value):
        """Serializes the value adding it to the parent element"""
        # Note that falsey values are not treated as missing, but they may be omitted.
        if value is None and self.required:
            raise MissingValue('Missing required value: "{}"'.format(self.element_name))

        if not value and self.omit_empty:
            return  # Do Nothing

        element = _element_get_or_add_from_parent(parent, self.element_name)
        self._serialize(element, value)

    def _parse_attribute(self, element):
        """Parses the primiteve value within the XML element's attribute"""
        parsed_value = self._default
        attribute_value = element.get(self._attribute, None)
        if attribute_value:
            parsed_value = self._parser_func(attribute_value)
        elif self.required:
            raise MissingValue('Missing required attribute "{}" on element "{}"'.format(
                self._attribute, self.element_name))

        return parsed_value

    def _serialize(self, element, value):
        """Serializes the value to the element"""
        # A value is only considered missing, and hence elegible to be replaced by its
        # default only if it is None. Falsey values are not considered missing and are
        # not replaced by the default.
        if value is None:
            serialized_value = str(self._default)
        else:
            serialized_value = str(value)

        if self._attribute:
            element.set(self._attribute, serialized_value)
        else:
            element.text = serialized_value


class _UserObject(object):
    """An XML processor for processing user-defined class instances"""

    def __init__(self, element_name, cls, child_processors, required=True, alias=None):
        self.element_name = element_name
        self.required = required
        self._cls = cls
        self._dictionary = _Dictionary(element_name, child_processors, required, alias)
        if alias:
            self.alias = alias
        else:
            self.alias = element_name

    def parse_at_element(self, element):
        """Parses the provided element as a user object"""
        parsed_dict = self._dictionary.parse_at_element(element)
        return self._dict_to_user_object(parsed_dict)

    def parse_at_root(self, root):
        """Parses the root XML element as a user object"""
        parsed_dict = self._dictionary.parse_at_root(root)
        return self._dict_to_user_object(parsed_dict)

    def parse_from_parent(self, parent):
        """Parses the user object data from the provided parent XML element"""
        parsed_dict = self._dictionary.parse_from_parent(parent)
        return self._dict_to_user_object(parsed_dict)

    def serialize(self, value):
        """
        Serializes the value to a new element and returns the element.
        """
        return self._dictionary.serialize(value.__dict__)

    def serialize_on_parent(self, parent, value):
        """Serializes the value and adds it to the parent"""
        self._dictionary.serialize_on_parent(parent, value.__dict__)

    def _dict_to_user_object(self, dict_value):
        """Converts the dictionary value to an instance of the user object"""
        value = self._cls()
        for field_name, field_value in dict_value.items():
            setattr(value, field_name, field_value)

        return value


def _element_get_or_add_from_parent(parent, element_name):
    """
    If an element with the give name has already been added to the parent element,
    then this returns the existing element. Otherwise, this will create a new element
    with the given name, append it to the parent, and return the newly created element.
    This allows for multiple values to be serialized to the same element which can occur
    if an element has any attributes.
    """
    element = parent.find(element_name)
    if element is None:
        element = ET.Element(element_name)
        parent.append(element)

    return element


def _is_valid_root_processor(processor):
    """Returns True if the given XML processor can be used as a root processor"""
    return hasattr(processor, 'parse_at_root')


def _parse_boolean(element_text):
    """Parses the raw XML string as a boolean value"""
    lowered_text = element_text.lower()
    if lowered_text == 'true':
        value = True
    elif lowered_text == 'false':
        value = False
    else:
        raise InvalidPrimitiveValue('Invalid boolean value: "{}"'.format(element_text))

    return value


def _parse_float(element_text):
    """Parses the raw XML string as a floating point value"""
    try:
        value = float(element_text)
    except ValueError:
        raise InvalidPrimitiveValue('Invalid float value: "{}"'.format(element_text))

    return value


def _parse_int(element_text):
    """Parses the raw XML string as an integer value"""
    try:
        value = int(element_text)
    except ValueError:
        raise InvalidPrimitiveValue('Invalid integer value: "{}"'.format(element_text))

    return value


def _parse_string(strip_whitespace):
    """Returns a parser function for parsing string values"""
    def _parse_string_value(element_text):
        if strip_whitespace:
            value = element_text.strip()
        else:
            value = element_text

        return value

    return _parse_string_value


def _xml_namespace_strip(root):
    """Strips the XML namespace prefix from all element tags under the given root Element"""
    if '}' not in root.tag:
        return  # Nothing to do, no namespace present

    for element in root.iter():
        if '}' in element.tag:
            element.tag = element.tag.split('}')[1]