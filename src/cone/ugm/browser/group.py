from plumber import plumber
from node.base import AttributedNode
from yafowil.base import factory, ExtractionError
from yafowil.common import ascii_extractor
from yafowil.utils import UNSET
from cone.tile import (
    tile,
    Tile,
)
from cone.app.browser.utils import (
    make_url,
    make_query,
)
from cone.app.browser.form import Form
from cone.app.browser.authoring import (
    AddPart,
    EditPart,
)
from cone.app.browser.ajax import AjaxAction
from cone.ugm.model.group import Group
from cone.ugm.model.utils import ugm_groups
from cone.ugm.browser.columns import Column
from cone.ugm.browser.listing import ColumnListing
from cone.ugm.browser.authoring import (
    AddFormFiddle,
    EditFormFiddle,
)
from webob.exc import HTTPFound


@tile('leftcolumn', interface=Group, permission='view')
class GroupLeftColumn(Column):

    add_label = u"Add Group"

    def render(self):
        setattr(self.request, '_curr_listing_id', self.model.name)
        return self._render(self.model.parent, 'leftcolumn')


@tile('rightcolumn', 'templates/right_column.pt',
      interface=Group, permission='view')
class GroupRightColumn(Tile):
    pass


class Principals(object):
    """Descriptor to return principal items for listing
    """
    def __init__(self, members_only=False):
        self.members_only = members_only

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self

        appgroup = obj.model
        group = appgroup.model
        member_ids = group.keys()
        
        # always True if we list members only, otherwise will be set
        # in the loop below
        related = self.members_only
        
        # XXX: so far only users as members of groups, for
        # group-in-group we need to prefix groups
        if self.members_only:
            users = group.users
        else:
            users = group.root.users.values()

        col_1_attr, col_2_attr, col_3_attr, sort_attr = obj.user_attrs
        ret = list()
        for user in users:
            id = user.name
            attrs = user.attrs
            
            item_target = make_url(obj.request, path=user.path[1:])
            action_query = make_query(id=id)
            action_target = make_url(obj.request,
                                     node=appgroup,
                                     query=action_query)

            if not self.members_only:
                related = id in member_ids

            action_id = 'add_item'
            action_enabled = not bool(related)
            action_title = 'Add user to selected group'
            add_item_action = obj.create_action(
                action_id, action_enabled, action_title, action_target)

            action_id = 'remove_item'
            action_enabled = bool(related)
            action_title = 'Remove user from selected group'
            remove_item_action = obj.create_action(
                action_id, action_enabled, action_title, action_target)

            actions = [add_item_action, remove_item_action]
            val_1 = obj.extract_raw(attrs, col_1_attr)
            val_2 = obj.extract_raw(attrs, col_2_attr)
            val_3 = obj.extract_raw(attrs, col_3_attr)
            content = obj.item_content(val_1, val_2, val_3)
            sort = obj.extract_raw(attrs, sort_attr)
            current = False
            item = obj.create_item(sort, item_target, content, current, actions)
            ret.append(item)
        return ret


@tile('columnlisting', 'templates/column_listing.pt',
      interface=Group, permission='view')
class UsersOfGroupColumnListing(ColumnListing):
    css = 'users'
    slot = 'rightlisting'
    list_columns = ColumnListing.user_list_columns
    # XXX: Why items and not keys() / __iter__?
    # used to be a readonly property
    query_items = Principals(members_only=True)
    batchname = 'rightbatch'


@tile('allcolumnlisting', 'templates/column_listing.pt',
      interface=Group, permission='view')
class AllUsersColumnListing(ColumnListing):
    css = 'users'
    slot = 'rightlisting'
    list_columns = ColumnListing.user_list_columns
    # XXX: Why items and not keys() / __iter__?
    # used to be a readonly property
    query_items = Principals()
    batchname = 'rightbatch'

    @property
    def ajax_action(self):
        return 'allcolumnlisting'


class GroupForm(object):

    @property
    def schema(self):
        # XXX: get info from config...
        return {
            'id': {
                'chain': 'field:*ascii:*exists:label:error:text',
                'props': {
                    'ascii': True},
                'custom': {
                    'ascii': ([ascii_extractor], [], [], []),
                    'exists': ([self.exists], [], [], [])
                    },
                }}

    @property
    def _protected_fields(self):
        # XXX: get info from config...
        return ['id']

    @property
    def _required_fields(self):
        # XXX: get info from config...
        return ['id']
    
    def prepare(self):
        resource = self.action_resource
        action = make_url(self.request, node=self.model, resource=resource)
        # create group form
        form = factory(
            u'form',
            name='groupform',
            props={
                'action': action,
            })
        settings = ugm_groups(self.model)
        attrmap = settings.attrs.groups_form_attrmap
        if not attrmap:
            return form
        schema = self.schema
        required = self._required_fields
        protected = self._protected_fields
        default_chain = 'field:label:error:text'
        for key, val in attrmap.items():
            field = schema.get(key, dict())
            chain = field.get('chain', default_chain)
            props = dict()
            props['label'] = val
            if key in required:
                props['required'] = 'No %s defined' % val
            props.update(field.get('props', dict()))
            value = UNSET
            mode = 'edit'
            if resource == 'edit':
                if key in protected:
                    mode = 'display'
                value = self.model.attrs.get(key, u'')
            form[key] = factory(
                chain,
                value=value,
                props=props,
                custom=field.get('custom', dict()),
                mode=mode)
        form['save'] = factory(
            'submit',
            props = {
                'action': 'save',
                'expression': True,
                'handler': self.save,
                'next': self.next,
                'label': 'Save',
            })
        if resource == 'add':
            form['cancel'] = factory(
                'submit',
                props = {
                    'action': 'cancel',
                    'expression': True,
                    'handler': None,
                    'next': self.next,
                    'label': 'Cancel',
                    'skip': True,
                })
        self.form = form

    def exists(self, widget, data):
        group_id = data.extracted
        if group_id is UNSET:
            return data.extracted
        if group_id in self.model.parent.backend:
            msg = "Group %s already exists." % (group_id,)
            raise ExtractionError(msg)
        return data.extracted


@tile('addform', interface=Group, permission="add")
class GroupAddForm(GroupForm, Form):
    __metaclass__ = plumber
    __plumbing__ = AddPart, AddFormFiddle
    
    show_heading = False

    def save(self, widget, data):
        settings = ugm_groups(self.model)
        attrmap = settings.attrs.groups_form_attrmap
        extracted = dict()
        for key, val in attrmap.items():
            val = data.fetch('groupform.%s' % key).extracted
            if not val:
                continue
            extracted[key] = val
        groups = self.model.parent.backend
        id = extracted.pop('id')
        group = groups.create(id, **extracted)
        self.request.environ['next_resource'] = id
        groups()
        self.model.parent.invalidate()
        # XXX: access already added user after invalidation.
        #      if not done, there's some kind of race condition with ajax
        #      continuation. figure out why.
        self.model.parent[id]

    def next(self, request):
        next_resource = self.request.environ.get('next_resource')
        if next_resource:
            url = make_url(request.request,
                           node=self.model,
                           resource=next_resource)
        else:
            url = make_url(request.request, node=self.model)
        if self.ajax_request:
            return [
                AjaxAction(url, 'leftcolumn', 'replace', '.left_column'),
                AjaxAction(url, 'rightcolumn', 'replace', '.right_column'),
            ]
        return HTTPFound(location=url)


@tile('editform', interface=Group, permission="edit")
class GroupEditForm(GroupForm, Form):
    __metaclass__ = plumber
    __plumbing__ = EditPart, EditFormFiddle
    
    show_heading = False

    def save(self, widget, data):
        settings = ugm_groups(self.model)
        attrmap = settings.attrs.groups_form_attrmap
        for key, val in attrmap.items():
            if key in ['id']:
                continue
            extracted = data.fetch('groupform.%s' % key).extracted
            self.model.attrs[key] = extracted
        self.model.model.context()
    
    def next(self, request):
        url = make_url(request.request, node=self.model)
        if self.ajax_request:
            return [
                AjaxAction(url, 'leftcolumn', 'replace', '.left_column'),
                AjaxAction(url, 'rightcolumn', 'replace', '.right_column'),
            ]
        return HTTPFound(location=url)