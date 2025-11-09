window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  delimiters: ['${', '}'],
  data: function () {
    return {
      currencyOptions: ['sat'],
      settingsFormDialog: {
        show: false,
        data: {}
      },

      padsFormDialog: {
        show: false,
        data: {
          name: null
        }
      },
      padsList: [],
      padsTable: {
        search: '',
        loading: false,
        columns: [
          {
            name: 'name',
            align: 'left',
            label: 'Pad name',
            field: 'name',
            sortable: true
          },
          {
            name: 'content',
            align: 'left',
            label: 'content',
            field: 'content',
            sortable: true
          },
          {
            name: 'updated_at',
            align: 'left',
            label: 'Updated At',
            field: 'updated_at',
            sortable: true
          },
          {name: 'id', align: 'left', label: 'ID', field: 'id', sortable: true}
        ],
        pagination: {
          sortBy: 'updated_at',
          rowsPerPage: 10,
          page: 1,
          descending: true,
          rowsNumber: 10
        }
      }
    }
  },
  watch: {
    'padsTable.search': {
      handler() {
        const props = {}
        if (this.padsTable.search) {
          props['search'] = this.padsTable.search
        }
        this.getPads()
      }
    }
  },

  methods: {
    //////////////// Pads ////////////////////////
    async showNewPadsForm() {
      this.padsFormDialog.data = {
        name: null
      }
      this.padsFormDialog.show = true
    },
    async showEditPadsForm(data) {
      this.padsFormDialog.data = {...data}
      this.padsFormDialog.show = true
    },
    async savePads() {
      try {
        const data = {extra: {}, ...this.padsFormDialog.data}
        const method = data.id ? 'PUT' : 'POST'
        const entry = data.id ? `/${data.id}` : ''
        await LNbits.api.request(
          method,
          '/chaospad/api/v1/pads' + entry,
          null,
          data
        )
        this.getPads()
        this.padsFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async getPads(props) {
      try {
        this.padsTable.loading = true
        const params = LNbits.utils.prepareFilterQuery(this.padsTable, props)
        const {data} = await LNbits.api.request(
          'GET',
          `/chaospad/api/v1/pads/paginated?${params}`,
          null
        )
        this.padsList = data.data
        this.padsTable.pagination.rowsNumber = data.total
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.padsTable.loading = false
      }
    },
    async deletePads(padsId) {
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Pads?')
        .onOk(async () => {
          try {
            await LNbits.api.request(
              'DELETE',
              '/chaospad/api/v1/pads/' + padsId,
              null
            )
            await this.getPads()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async exportPadsCSV() {
      await LNbits.utils.exportCSV(
        this.padsTable.columns,
        this.padsList,
        'pads_' + new Date().toISOString().slice(0, 10) + '.csv'
      )
    },

    //////////////// Utils ////////////////////////
    dateFromNow(date) {
      return moment(date).fromNow()
    }
  },
  ///////////////////////////////////////////////////
  //////LIFECYCLE FUNCTIONS RUNNING ON PAGE LOAD/////
  ///////////////////////////////////////////////////
  async created() {
    this.getPads()
  }
})
