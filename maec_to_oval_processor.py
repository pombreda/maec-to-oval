#MAEC -> OVAL Translator
#v0.94 BETA
#Processor Class
import oval57 as oval #bindings
import cybox_oval_mappings
import sys
import os
import traceback
import datetime
import maec.bindings.maec_bundle as bundle_binding
import maec.bindings.maec_package as package_binding
from maec.package.package import Package
from maec.bundle.bundle import Bundle

class maec_to_oval_processor(object):
    def __init__(self, infilename, outfilename, verbose_mode, stat_mode):
        self.converted_ids = []
        self.skipped_actions = []
        self.oval_defs = oval.DefinitionsType()
        self.oval_tests = oval.TestsType()
        self.oval_objects = oval.ObjectsType()
        self.oval_states = oval.StatesType()
        self.ovaldefroot = oval.oval_definitions()
        self.mappings = cybox_oval_mappings.cybox_oval_mappings('maec_to_oval')
        self.supported_action_types = ['create', 'modify']
        self.metadata = oval.MetadataType(title = 'Object check', description = 'Existence check for object(s) extracted from MAEC Action')
        self.infilename = infilename
        self.outfilename = outfilename
        self.verbose_mode = verbose_mode
        self.stat_mode = stat_mode
        self.current_bundle = None

    #Process an associated object and create the corresponding OVAL
    def process_associated_object(self, associated_object, action_id, actual_object = None):
        #Only process 'affected' objects (those that were manipulated/instantiated as a result of the action)
        if associated_object.association_type is not None and associated_object.association_type.value in ['input', 'output', 'side-effect']:
            # Corner case for handling Objects passed in as a result of de-referencing
            if actual_object:
                object_properties = actual_object._properties
            else:
                object_properties = associated_object._properties
            if object_properties:
                oval_entities = self.mappings.create_oval(object_properties, action_id)
                if oval_entities is not None:
                    #Create a new OVAL definition
                    oval_def = oval.DefinitionType(version = 1.0, id = self.mappings.generate_def_id(), classxx = 'miscellaneous', metadata = self.metadata)
                    oval_criteria = oval.CriteriaType()
                    #Add the tests, objects, and states to the oval document
                    self.oval_tests.add_test(oval_entities.get('test'))
                    self.oval_objects.add_object(oval_entities.get('object'))
                    if oval_entities.has_key('state'):
                        for oval_state in oval_entities.get('state'):
                            self.oval_states.add_state(oval_state)
                    #Create the criterion and add it to the criteria
                    oval_criterion = oval.CriterionType(test_ref = oval_entities.get('test').id)
                    oval_criteria.add_criterion(oval_criterion)
                    if oval_criteria.hasContent_():
                        oval_def.set_criteria(oval_criteria)
                        self.oval_defs.add_definition(oval_def)
                        return True
                    return False
                else:
                    return False
            else:
                return False
        else:
            return False

    #Process an individual MAEC action
    def process_action(self, action):
        if action.id_ is not None and action.name.value.split(' ')[0] in self.supported_action_types:
            # Check the Action status - only successful or completed Actions should be converted
            if action.action_status and (action.action_status not in ["Success", "Complete/Finish"]):
                self.skipped_actions.append(action.id_)
                return
            converted = False
            associated_objects = action.associated_objects
            if associated_objects is not None and len(associated_objects) > 0:
                for associated_object in associated_objects:
                    # Dereference any Associated_Objects that are specified by IDREF
                    if associated_object.idref:
                        actual_object = self.current_bundle.get_object_by_id(associated_object.idref)
                        converted = (converted or self.process_associated_object(associated_object, action.id_, actual_object))
                    else:
                        converted = (converted or self.process_associated_object(associated_object, action.id_))
                if converted:
                    self.converted_ids.append(action.id_)
                else:
                    self.skipped_actions.append(action.id_)
            else:
                self.skipped_actions.append(action.id_)
        else:
            self.skipped_actions.append(action.id_)

    #Process an individual behavior collection
    def process_behavior_collection(self, behavior_collection):
        behavior_list = behavior_collection.behavior_list
        if behavior_list is not None and len(behavior_list) > 0:
            self.process_behavior(behavior_list)

    #Process an individual action collection
    def process_action_collection(self, action_collection):
        action_list = action_collection.action_list
        if action_list is not None and len(action_list) > 0:
            self.process_actions(action_list)

    #Process an individual MAEC behavior
    def process_behavior(self, behavior):
        behavioral_actions = behavior.action_list
        if behavioral_actions is not None:
            #Handle any actions that represent the behavior
            for action in behavioral_actions:
                self.process_action(action)

    #Process any list of behaviors
    def process_behaviors(self, behaviors):
        for behavior in behaviors:
            self.process_behavior(behavior)

    #Process any list of actions
    def process_actions(self, actions):
        for action in actions:
            self.process_action(action)

    #Process the top-level collections
    def process_collections(self, collections):
        if collections.action_collections is not None:
            for action_collection in collections.action_collections:
                self.process_action_collection(action_collection)
        if collections.behavior_collections is not None:
            for behavior_collection in collections.behavior_collections:
                self.process_behavior_collection(behavior_collection)

    #Process the MAEC Bundle and extract any actions
    def process_bundle(self, maec_bundle):
        # Set the current bundle
        self.current_bundle = maec_bundle
        #Parse any behaviors in the root-level <behaviors> element
        top_level_behaviors = maec_bundle.behaviors
        if top_level_behaviors is not None:
            self.process_behaviors(top_level_behaviors)
        #Parse any actions in the root-level <actions> element
        top_level_actions = maec_bundle.actions
        if top_level_actions is not None and len(top_level_actions) > 0:
            self.process_actions(top_level_actions)
        #Parse any action collections in the top-level <collections> element
        top_level_collections = maec_bundle.collections
        if top_level_collections is not None:
            self.process_collections(top_level_collections)
            
    #Generate OVAL output from the MAEC Bundle
    def generate_oval(self):
        #Basic input file checking
        if os.path.isfile(self.infilename):    
            #Try parsing the MAEC file with both bindings
            package_obj = package_binding.parse(self.infilename)
            bundle_obj = bundle_binding.parse(self.infilename)
            try:
                sys.stdout.write('Generating ' + self.outfilename + ' from ' + self.infilename + '...')
                #Test whether the input is a Package or Bundle and process accordingly
                if bundle_obj.hasContent_():
                    maec_bundle = Bundle.from_obj(bundle_obj)
                    self.process_bundle(maec_bundle)
                elif package_obj.hasContent_():
                    maec_package = Package.from_obj(package_obj)
                    for malware_subject in maec_package.malware_subjects:
                        for maec_bundle in malware_subject.findings_bundles.bundles:
                            self.process_bundle(maec_bundle)

                #Build up the OVAL document from the parsed data and corresponding objects
                self.__build_oval_document()

                if len(self.converted_ids) > 0:
                    #Export to the output file
                    outfile = open(self.outfilename, 'w')
                    self.ovaldefroot.export(outfile, 0, namespacedef_='xmlns="http://oval.mitre.org/XMLSchema/oval-definitions-5" xmlns:oval-def="http://oval.mitre.org/XMLSchema/oval-definitions-5" xmlns:win-def="http://oval.mitre.org/XMLSchema/oval-definitions-5#windows" xmlns:oval="http://oval.mitre.org/XMLSchema/oval-common-5" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://oval.mitre.org/XMLSchema/oval-definitions-5#windows http://oval.mitre.org/language/version5.7/ovaldefinition/complete/windows-definitions-schema.xsd http://oval.mitre.org/XMLSchema/oval-definitions-5 http://oval.mitre.org/language/version5.7/ovaldefinition/complete/oval-definitions-schema.xsd http://oval.mitre.org/XMLSchema/oval-common-5 http://oval.mitre.org/language/version5.7/ovaldefinition/complete/oval-common-schema.xsd"')
                    sys.stdout.write('Done\n')
                else:
                    sys.stdout.write('no OVAL output written; 0 actions were converted.\n')
                if self.stat_mode:
                    print '\n**Converted Actions**'
                    for action_id in self.converted_ids:
                        print 'Action ' + action_id + ' converted successfully'
                    print '**Skipped Actions**'
                    for action_id in self.skipped_actions:
                        print 'Action ' + action_id + ' skipped; incompatible action/object type or missing object attributes'

            except Exception, err:
                print('\nError: %s\n' % str(err))
                if self.verbose_mode:
                    traceback.print_exc()
           
        else:
            print('\nError: Input file not found or inaccessible.')
            sys.exit(1)

    #Helper methods
    def __generate_datetime(self):
        dtime = datetime.datetime.now().isoformat()
        return dtime

    def __build_oval_document(self):
        #Add the generator to the defs
        oval_gen = oval.GeneratorType()
        oval_gen.set_product_name('MAEC XML to OVAL Script')
        oval_gen.set_product_version('0.94')
        oval_gen.set_schema_version('5.7')
        #Generate the datetime
        oval_gen.set_timestamp(self.__generate_datetime())

        #Add the definitions, tests, objects, and generator to the root OVAL document
        self.ovaldefroot.set_definitions(self.oval_defs)
        self.ovaldefroot.set_tests(self.oval_tests)
        self.ovaldefroot.set_objects(self.oval_objects)
        if self.oval_states.hasContent_():
            self.ovaldefroot.set_states(self.oval_states)
        self.ovaldefroot.set_generator(oval_gen)
    
